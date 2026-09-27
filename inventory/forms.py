from django import forms
from .models import Product


class ProductCreateForm(forms.ModelForm):
    stock = forms.IntegerField(
        label="初期在庫",
        min_value=0,
        initial=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
    )

    class Meta:
        model = Product
        fields = ["name", "rakuten_url", "stock"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "例: 洗剤A"}),
            "rakuten_url": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://item.rakuten.co.jp/..."}),
        }


class ProductEditForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "rakuten_url", "stock", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "rakuten_url": forms.URLInput(attrs={"class": "form-control"}),
            "stock": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
