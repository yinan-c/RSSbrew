from django import forms
from .models import Filter, Article

class FilterForm(forms.ModelForm):
    class Meta:
        model = Filter
        fields = '__all__'
        widgets = {
            'value': forms.Textarea(attrs={'cols': 20, 'rows': 1}),
        }

class ReadOnlyArticleForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = '__all__'
        widgets = {
            'content': forms.HiddenInput(),
        }