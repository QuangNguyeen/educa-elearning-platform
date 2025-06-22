from django.shortcuts import redirect, get_object_or_404
from django.views.generic import DetailView
from django.views.generic.base import TemplateResponseMixin, View
from django.views.generic.list import ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
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


# --- IV. Content CRUD Views using Template Method Pattern (Đúng 100%) ---
# Lớp cơ sở trừu tượng định nghĩa "bộ xương" thuật toán CRUD cho Content
class BaseContentCRUDView(TemplateResponseMixin, View):
    module = None
    model = None  # Biến để lưu trữ Model của nội dung (Text, Video, etc.)
    obj = None
    template_name = 'courses/manage/content/form.html'

    def _get_content_model_class(self): # Không còn model_name là tham số
        """[HOOK] Trả về lớp Model cụ thể (Text, Video, Image, File).
        Lớp con sẽ xác định model cụ thể này.
        """
        raise NotImplementedError("Subclasses must implement _get_content_model_class.")

    def _get_content_form_class(self, model, *args, **kwargs):
        """[HOOK] Trả về lớp Form (ModelForm) cho model nội dung cụ thể."""
        raise NotImplementedError("Subclasses must implement _get_content_form_class.")

    def _on_content_item_saved(self, obj, is_new):
        """[HOOK] Thực hiện các hành động sau khi đối tượng nội dung được lưu."""
        raise NotImplementedError("Subclasses must implement _on_content_item_saved.")

    def dispatch(self, request, module_id, id=None): # Bỏ model_name khỏi dispatch
        self.module = get_object_or_404(Module, id=module_id, course__owner=request.user)
        self.model = self._get_content_model_class() # Gọi Hook để lấy Model
        if not self.model: # Lỗi nếu hook trả về None
            raise Http404("Invalid content model configured for this view.")
        if id:
            self.obj = get_object_or_404(self.model, id=id, owner=request.user)
        return super().dispatch(request, module_id, id)

    def get(self, request, module_id, id=None): # Bỏ model_name khỏi get
        form = self._get_content_form_class(self.model, instance=self.obj)
        return self.render_to_response({'form': form, 'object': self.obj})

    def post(self, request, module_id, id=None): # Bỏ model_name khỏi post
        form = self._get_content_form_class(self.model, instance=self.obj, data=request.POST, files=request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.owner = request.user
            obj.save()
            self._on_content_item_saved(obj, is_new=not id)
            return redirect('module_content_list', self.module.id)
        return self.render_to_response({'form': form, 'object': self.obj})


# --- Concrete Classes (Triển khai cụ thể cho từng loại Content) ---

# View để quản lý nội dung Text
class TextContentCreateUpdateView(BaseContentCRUDView):
    def _get_content_model_class(self):
        return Text

    def _get_content_form_class(self, model, *args, **kwargs):
        return modelform_factory(Text, exclude=['owner', 'order', 'created', 'updated'])(*args, **kwargs)

    def _on_content_item_saved(self, obj, is_new):
        if is_new:
            Content.objects.create(module=self.module, item=obj)

# View để quản lý nội dung Video
class VideoContentCreateUpdateView(BaseContentCRUDView):
    def _get_content_model_class(self):
        return Video

    def _get_content_form_class(self, model, *args, **kwargs):
        return modelform_factory(Video, exclude=['owner', 'order', 'created', 'updated'])(*args, **kwargs)

    def _on_content_item_saved(self, obj, is_new):
        if is_new:
            Content.objects.create(module=self.module, item=obj)

# View để quản lý nội dung Image
class ImageContentCreateUpdateView(BaseContentCRUDView):
    def _get_content_model_class(self):
        return Image

    def _get_content_form_class(self, model, *args, **kwargs):
        return modelform_factory(Image, exclude=['owner', 'order', 'created', 'updated'])(*args, **kwargs)

    def _on_content_item_saved(self, obj, is_new):
        if is_new:
            Content.objects.create(module=self.module, item=obj)

# View để quản lý nội dung File
class FileContentCreateUpdateView(BaseContentCRUDView):
    def _get_content_model_class(self):
        return File

    def _get_content_form_class(self, model, *args, **kwargs):
        return modelform_factory(File, exclude=['owner', 'order', 'created', 'updated'])(*args, **kwargs)

    def _on_content_item_saved(self, obj, is_new):
        if is_new:
            Content.objects.create(module=self.module, item=obj)

# View để xóa Content (Không thay đổi, không thuộc Template Method)
class ContentDeleteView(View):
    def post(self, request, id):
        content = get_object_or_404(Content, id=id, module__course__owner=request.user)
        module = content.module
        content.item.delete()
        content.delete()
        return redirect('module_content_list', module.id)


# --- V. Các Mixin và Views cho việc sắp xếp lại thứ tự (Order) ---
class OrderUpdateMixin(CsrfExemptMixin, JsonRequestResponseMixin, View):
    model_class = None
    filter_field = None
    order_field = 'order'

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
    filter_field = 'course__owner'


class ContentOrderView(OrderUpdateMixin):
    model_class = Content
    filter_field = 'module__course__owner'


# --- VI. Các Views hiển thị danh sách và chi tiết Course công khai ---
class CacheCourseListMixin(object):
    """Mixin để thêm caching cho danh sách Course và Subject."""

    def get(self, request, subject=None, *args, **kwargs):
        subjects = cache.get('all_subjects')
        if not subjects:
            subjects = Subject.objects.annotate(total_courses=Count('courses'))
            cache.set('all_subjects', subjects, 60 * 15)

        all_courses_queryset = Course.objects.annotate(total_modules=Count('modules'))

        if subject:
            subject_obj = get_object_or_404(Subject, slug=subject)
            key = f'subject_{subject_obj.id}_courses'
            courses = cache.get(key)
            if not courses:
                courses = all_courses_queryset.filter(subject=subject_obj)
                cache.set(key, courses, 60 * 15)
        else:
            courses = cache.get('all_courses')
            if not courses:
                courses = all_courses_queryset
                cache.set('all_courses', courses, 60 * 15)

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
