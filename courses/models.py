from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.template.loader import render_to_string
from .fields import OrderField

class Component:
    @property
    def children(self):
        return []

    def add(self, child):
        pass

    def remove(self, child):
        pass

    def is_composite(self):
        return False

class Subject(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    class Meta:
        ordering = ['title']
    def __str__(self):
        return self.title

class Course(models.Model, Component):
    owner = models.ForeignKey(User, related_name='courses_created', on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, related_name='courses', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    overview = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    students = models.ManyToManyField(User, related_name='courses_joined', blank=True)

    class Meta:
        ordering = ['-created']

    def __str__(self):
        return self.title

    @property
    def children(self):
        """
        Trả về danh sách các module thuộc khóa học này (Composite pattern).
        """
        return self.modules.all()

    def is_composite(self):
        """
        Khóa học là composite vì có thể chứa nhiều module.
        """
        return True

    def add(self, child):
        """
        Thêm một module vào khóa học này.
        """
        child.course = self
        child.save()

    def remove(self, child):
        """
        Xóa một module khỏi khóa học này.
        """
        child.delete()

    def get_modules(self):
        """
        Lấy danh sách các module của khóa học.
        """
        return self.modules.all()

class Module(models.Model, Component):
    course = models.ForeignKey(Course, related_name='modules', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = OrderField(blank=True, for_fields=['course'])

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'{self.title} (Module)'

    @property
    def children(self):
        """
        Trả về danh sách các content thuộc module này (Composite pattern).
        """
        return self.contents.all()

    def is_composite(self):
        """
        Module là composite vì có thể chứa nhiều content.
        """
        return True

    def add(self, child):
        """
        Thêm một content vào module này.
        """
        child.module = self
        child.save()

    def remove(self, child):
        """
        Xóa một content khỏi module này.
        """
        child.delete()

    def get_contents(self):
        """
        Lấy danh sách các content của module.
        """
        return self.contents.all()

class Content(models.Model, Component):
    module = models.ForeignKey(Module, related_name='contents', on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    item = GenericForeignKey('content_type', 'object_id')
    order = OrderField(blank=True, for_fields=['module'])
    class Meta:
        ordering = ['order']
    @property
    def children(self):
        if hasattr(self.item, 'children'):
            return self.item.children
        return []

    def is_composite(self):
        return bool(self.children)

class ItemBase(models.Model, Component):
    owner = models.ForeignKey(User, related_name='%(class)s_related', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.title

    def render(self):
        return render_to_string(f'courses/content/{self._meta.model_name}.html', {'item': self})

# Concrete item classes
class Text(ItemBase):
    content = models.TextField()

class File(ItemBase):
    file = models.FileField(upload_to='files')

class Image(ItemBase):
    file = models.ImageField(upload_to='images')

class Video(ItemBase):
    url = models.URLField()