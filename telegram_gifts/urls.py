from django.contrib import admin
from django.urls import path
from gifts_app.views import index, get_collections, get_nfts, create_payment, upload_data, payment_result, details, reviews

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', index, name='index'),
    path('api/collections/', get_collections, name='get_collections'),
    path('api/nfts/<str:collection_id>/', get_nfts, name='get_nfts'),
    path('api/create-payment/', create_payment, name='create_payment'),
    path('api/upload-data/', upload_data, name='upload_data'),
    path('api/payment-result/', index, name='payment_result'),
    path('fail/', index, name='fail'),
    path('details/', details, name='details'),
    path('reviews/', reviews, name='reviews')  # Новый маршрут
]