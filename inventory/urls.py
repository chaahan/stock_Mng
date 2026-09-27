from django.urls import path
from . import views

urlpatterns = [
    # General app pages
    path("", views.home, name="home"),
    path("products/<int:pk>/", views.product_detail, name="product_detail"),
    path("q/<str:qr_token>/", views.qr_process, name="qr_process"),
    path("q/<str:qr_token>/image/", views.generate_qr_image, name="generate_qr_image"),

    # Custom management pages
    path("manage/", views.manage_product_list, name="manage_product_list"),
    path("manage/products/add/", views.manage_product_create, name="manage_product_create"),
    path("manage/products/<int:pk>/edit/", views.manage_product_edit, name="manage_product_edit"),
    path("manage/products/<int:pk>/qr/", views.manage_product_qr, name="manage_product_qr"),
]
