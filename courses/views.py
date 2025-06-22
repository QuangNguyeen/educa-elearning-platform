from django.shortcuts import redirect, get_object_or_404
from django.views.generic import DetailView
from django.views.generic.base import TemplateResponseMixin, View
from django.views.generic.list import ListView
from django.views.generic.edit import CreateView, UpdateView, \
    DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, \
    PermissionRequiredMixin
from django.urls import reverse_lazy
from django.forms.models import modelform_factory
from django.apps import apps
from django.db.models import Count
from django.core.cache import cache
from django.http import Http404
from braces.views import CsrfExemptMixin, JsonRequestResponseMixin

# Import các models và forms cần thiết
from students.forms import CourseEnrollForm
from .forms import ModuleFormSet
from .models import Course, Module, Content, Subject, Text, File, Image, Video
from .fields import OrderField  # Giả định OrderField nằm trong file fields.py cùng cấp


# --- I. Các Mixin cơ sở cho quyền sở hữu và chỉnh sửa ---
# Đây là các mixin đã có, giúp quản lý quyền sở hữu đối tượng
class OwnerMixin:
    """Mixin để lọc queryset theo người sở hữu hiện tại."""

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(owner=self.request.user)


class OwnerEditMixin:
    """Mixin để gán người sở hữu cho đối tượng khi tạo/cập nhật."""

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class OwnerCourseMixin(OwnerMixin,
                       LoginRequiredMixin,
                       PermissionRequiredMixin):
    """Mixin cơ bản cho các View quản lý Course của người sở hữu."""
    model = Course
    fields = ['subject', 'title', 'slug', 'overview']
    success_url = reverse_lazy('manage_course_list')


class OwnerCourseEditMixin(OwnerCourseMixin, OwnerEditMixin):
    """Mixin cho các View tạo/cập nhật Course của người sở hữu."""
    template_name = 'courses/manage/course/form.html'


# --- II. Các Views quản lý Course (CRUD) ---
# Sử dụng các mixin Owner đã định nghĩa
class ManageCourseListView(OwnerCourseMixin, ListView):
    template_name = 'courses/manage/course/list.html'
    permission_required = 'courses.view_course'


class CourseCreateView(OwnerCourseEditMixin, CreateView):
    permission_required = 'courses.add_course'


class CourseUpdateView(OwnerCourseEditMixin, UpdateView):
    permission_required = 'courses.change_course'


class CourseDeleteView(OwnerCourseMixin, DeleteView):
    template_name = 'courses/manage/course/delete.html'
    permission_required = 'courses.delete_course'


# --- III. Các Views quản lý Module ---
# ModuleFormSet đã là một công cụ mạnh mẽ, View này xử lý formset cho Module
class CourseModuleUpdateView(TemplateResponseMixin, View):
    template_name = 'courses/manage/module/formset.html'
    course = None

    def get_formset(self, data=None):
        return ModuleFormSet(instance=self.course,
                             data=data)

    def dispatch(self, request, pk):
        self.course = get_object_or_404(Course,
                                        id=pk,
                                        owner=request.user)
        return super().dispatch(request, pk)

    def get(self, request, *args, **kwargs):
        formset = self.get_formset()
        return self.render_to_response({'course': self.course,
                                        'formset': formset})

    def post(self, request, *args, **kwargs):
        formset = self.get_formset(data=request.POST)
        if formset.is_valid():
            formset.save()
            return redirect('manage_course_list')
        return self.render_to_response({'course': self.course,
                                        'formset': formset})


class ModuleContentListView(TemplateResponseMixin, View):
    template_name = 'courses/manage/module/content_list.html'

    def get(self, request, module_id):
        module = get_object_or_404(Module,
                                   id=module_id,
                                   course__owner=request.user)
        return self.render_to_response({'module': module})


# --- IV. Các Views quản lý Content (Sử dụng Template Method Pattern) ---
# Lớp cơ sở trừu tượng định nghĩa "bộ xương" thuật toán CRUD cho Content
class BaseContentCRUDView(TemplateResponseMixin, View):
    module = None
    model = None
    obj = None
    template_name = 'courses/manage/content/form.html'

    def _get_content_model_class(self, model_name):
        """[HOOK] Trả về lớp Model cụ thể (Text, Video, Image, File)."""
        raise NotImplementedError("Subclasses must implement _get_content_model_class.")

    def _get_content_form_class(self, model, *args, **kwargs):
        """[HOOK] Trả về lớp Form (ModelForm) cho model nội dung cụ thể."""
        raise NotImplementedError("Subclasses must implement _get_content_form_class.")

    def _on_content_item_saved(self, obj, is_new):
        """[HOOK] Thực hiện các hành động sau khi đối tượng nội dung được lưu."""
        raise NotImplementedError("Subclasses must implement _on_content_item_saved.")

    def dispatch(self, request, module_id, model_name, id=None):
        self.module = get_object_or_404(Module, id=module_id, course__owner=request.user)
        self.model = self._get_content_model_class(model_name)
        if not self.model:
            raise Http404("Invalid content model.")
        if id:
            self.obj = get_object_or_404(self.model, id=id, owner=request.user)
        return super().dispatch(request, module_id, model_name, id)

    def get(self, request, module_id, model_name, id=None):
        form = self._get_content_form_class(self.model, instance=self.obj)
        return self.render_to_response({'form': form, 'object': self.obj})

    def post(self, request, module_id, model_name, id=None):
        form = self._get_content_form_class(self.model, instance=self.obj, data=request.POST, files=request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.owner = request.user
            obj.save()
            self._on_content_item_saved(obj, is_new=not id)
            return redirect('module_content_list', self.module.id)
        return self.render_to_response({'form': form, 'object': self.obj})


# Lớp cụ thể triển khai CRUD cho Content
class ContentCreateUpdateView(BaseContentCRUDView):
    def _get_content_model_class(self, model_name):
        if model_name in ['text', 'video', 'image', 'file']:
            return apps.get_model(app_label='courses', model_name=model_name)
        return None

    def _get_content_form_class(self, model, *args, **kwargs):
        return modelform_factory(model, exclude=['owner', 'order', 'created', 'updated'])(*args, **kwargs)

    def _on_content_item_saved(self, obj, is_new):
        if is_new:
            Content.objects.create(module=self.module, item=obj)


# View để xóa Content
class ContentDeleteView(View):
    def post(self, request, id):
        content = get_object_or_404(Content, id=id, module__course__owner=request.user)
        module = content.module
        content.item.delete()
        content.delete()
        return redirect('module_content_list', module.id)


# --- V. Các Mixin và Views cho việc sắp xếp lại thứ tự (Order) ---
# Mixin chung cho việc cập nhật thứ tự các đối tượng
class OrderUpdateMixin(CsrfExemptMixin, JsonRequestResponseMixin, View):
    model_class = None  # Model class to update (e.g., Module, Content)
    filter_field = None  # Field to filter by owner/course__owner
    order_field = 'order'  # Field to store order

    def post(self, request, *args, **kwargs):
        if not self.model_class or not self.filter_field:
            raise NotImplementedError("model_class and filter_field must be set in subclasses.")

        try:
            for id, order in self.request_json.items():
                filter_kwargs = {
                    'id': id,
                    self.filter_field: request.user
                }
                self.model_class.objects.filter(**filter_kwargs).update(**{self.order_field: order})
            return self.render_json_response({'saved': 'OK'})
        except Exception as e:
            return self.render_json_response({'error': str(e)}, status=400)


class ModuleOrderView(OrderUpdateMixin):
    model_class = Module
    filter_field = 'course__owner'  # Module is filtered by its course's owner


class ContentOrderView(OrderUpdateMixin):
    model_class = Content
    filter_field = 'module__course__owner'  # Content is filtered by its module's course's owner


# --- VI. Các Views hiển thị danh sách và chi tiết Course công khai ---
class CacheCourseListMixin(object):
    """Mixin để thêm caching cho danh sách Course và Subject."""

    def get(self, request, subject=None, *args, **kwargs):
        subjects = cache.get('all_subjects')
        if not subjects:
            subjects = Subject.objects.annotate(total_courses=Count('courses'))
            cache.set('all_subjects', subjects, 60 * 15)  # Cache for 15 minutes

        all_courses_queryset = Course.objects.annotate(total_modules=Count('modules'))

        if subject:
            subject_obj = get_object_or_404(Subject, slug=subject)
            key = f'subject_{subject_obj.id}_courses'
            courses = cache.get(key)
            if not courses:
                courses = all_courses_queryset.filter(subject=subject_obj)
                cache.set(key, courses, 60 * 15)  # Cache for 15 minutes
        else:
            courses = cache.get('all_courses')
            if not courses:
                courses = all_courses_queryset
                cache.set('all_courses', courses, 60 * 15)  # Cache for 15 minutes

        return self.render_to_response({'subjects': subjects,
                                        'subject': subject_obj if subject else None,
                                        'courses': courses})


class CourseListView(CacheCourseListMixin, TemplateResponseMixin, View):
    template_name = 'courses/course/list.html'


class CourseDetailView(DetailView):
    model = Course
    template_name = 'courses/course/detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['enroll_form'] = CourseEnrollForm(initial={'course': self.object})
        return context

