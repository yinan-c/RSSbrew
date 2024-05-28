from django import forms
from .models import Filter, Article, ProcessedFeed
from django.contrib import admin

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

class ProcessedFeedAdminForm(forms.ModelForm):
    class Meta:
        model = ProcessedFeed
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(ProcessedFeedAdminForm, self).__init__(*args, **kwargs)
#        toggle_digest_initial = self.initial.get('toggle_digest', self.instance.toggle_digest if self.instance else False)
#        if not toggle_digest_initial:
#            self.fields['digest_frequency'].widget = forms.HiddenInput()
#            self.fields['digest_time'].widget = forms.HiddenInput()
#            self.fields['additional_prompt_for_digest'].widget = forms.HiddenInput()
#            self.fields['send_full_article'].widget = forms.HiddenInput()
