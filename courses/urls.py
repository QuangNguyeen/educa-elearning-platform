from django.urls import path
from . import views

urlpatterns = [
    # Course Management Views
    path('mine/', views.ManageCourseListView.as_view(), name='manage_course_list'),
    path('create/', views.CourseCreateView.as_view(), name='course_create'),
    path('<pk>/edit/', views.CourseUpdateView.as_view(), name='course_edit'),
    path('<pk>/delete/', views.CourseDeleteView.as_view(), name='course_delete'),
    path('<pk>/module/', views.CourseModuleUpdateView.as_view(), name='course_module_update'),

    # Module Content List View
    path('module/<int:module_id>/', views.ModuleContentListView.as_view(), name='module_content_list'),

    # Content CRUD Views (specific for each content type)
    # Text Content
    path('module/<int:module_id>/content/text/create/',
         views.TextContentCreateUpdateView.as_view(),
         name='module_content_create_text'),
    path('module/<int:module_id>/content/text/<int:id>/update/',
         views.TextContentCreateUpdateView.as_view(),
         name='module_content_update_text'),

    # Video Content
    path('module/<int:module_id>/content/video/create/',
         views.VideoContentCreateUpdateView.as_view(),
         name='module_content_create_video'),
    path('module/<int:module_id>/content/video/<int:id>/update/',
         views.VideoContentCreateUpdateView.as_view(),
         name='module_content_update_video'),

    # Image Content
    path('module/<int:module_id>/content/image/create/',
         views.ImageContentCreateUpdateView.as_view(),
         name='module_content_create_image'),
    path('module/<int:module_id>/content/image/<int:id>/update/',
         views.ImageContentCreateUpdateView.as_view(),
         name='module_content_update_image'),

    # File Content
    path('module/<int:module_id>/content/file/create/',
         views.FileContentCreateUpdateView.as_view(),
         name='module_content_create_file'),
    path('module/<int:module_id>/content/file/<int:id>/update/',
         views.FileContentCreateUpdateView.as_view(),
         name='module_content_update_file'),

    # Content Delete View (still generic by ID)
    path('content/<int:id>/delete/', views.ContentDeleteView.as_view(), name='module_content_delete'),

    # Order Update Views
    path('module/order/', views.ModuleOrderView.as_view(), name='module_order'),
    path('content/order/', views.ContentOrderView.as_view(), name='content_order'),

    # Public Course Listing/Detail Views
    path('subject/<slug:subject>/', views.CourseListView.as_view(), name='course_list_subject'),
    path('<slug:slug>/', views.CourseDetailView.as_view(), name='course_detail'),
]
