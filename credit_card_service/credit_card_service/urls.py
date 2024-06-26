"""
URL configuration for credit_card_service project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from user.views import *
from repayment.views import *

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/register-user/', RegisterUserView.as_view(), name='register-user'),
    path('api/apply-loan/', ApplyLoanView.as_view(), name='apply-loan'),
    path('api/make-payment/', MakePaymentView.as_view(), name='make-payment'),
    path('api/get-statement/', StatementView.as_view(), name='get-statement')
]
