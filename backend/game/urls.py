from django.urls import include,path
from rest_framework.routers import DefaultRouter
from .views import RoomViewSet,QuestionViewSet
router=DefaultRouter(); router.register('rooms',RoomViewSet)
questions=QuestionViewSet.as_view({'get':'list','post':'create'})
question=QuestionViewSet.as_view({'get':'retrieve','put':'update','patch':'partial_update','delete':'destroy'})
urlpatterns=[
    path('',include(router.urls)),
    path('rooms/<str:room_code>/questions/',questions),
    path('rooms/<str:room_code>/questions/<int:pk>/',question),
]
