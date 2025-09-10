from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Article, Filter, ProcessedFeed


class FilterForm(forms.ModelForm):
    class Meta:
        model = Filter
        fields = ["filter_group", "field", "match_type", "value"]
        widgets = {
            "value": forms.Textarea(attrs={"cols": 20, "rows": 1}),
        }


class ReadOnlyArticleForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = [
            "original_feed",
            "title",
            "link",
            "published_date",
            "content",
            "summary",
            "summarized",
            "summary_one_line",
            "custom_prompt",
        ]
        widgets = {
            "content": forms.HiddenInput(),
        }


class ProcessedFeedAdminForm(forms.ModelForm):
    class Meta:
        model = ProcessedFeed
        fields = [
            "name",
            "feeds",
            "articles_to_summarize_per_interval",
            "summary_language",
            "additional_prompt",
            "translate_title",
            "model",
            "other_model",
            "toggle_digest",
            "toggle_entries",
            "digest_frequency",
            "last_digest",
            "include_toc",
            "include_one_line_summary",
            "include_summary",
            "include_content",
            "use_ai_digest",
            "send_full_article",
            "additional_prompt_for_digest",
            "digest_model",
            "other_digest_model",
            "feed_group_relational_operator",
            "summary_group_relational_operator",
            "case_sensitive",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data is None:
            cleaned_data = {}

        feeds = cleaned_data.get('feeds')
        include_tags = cleaned_data.get('include_tags')

        # Check if at least one of feeds or include_tags is provided
        if not feeds and not include_tags:
            raise forms.ValidationError(
                _("At least one original feed or tag must be selected. "
                  "You can either select specific feeds directly or choose tags to include all feeds with those tags.")
            )

        return cleaned_data


#        toggle_digest_initial = self.initial.get('toggle_digest', self.instance.toggle_digest if self.instance else False)
#        if not toggle_digest_initial:
#            self.fields['digest_frequency'].widget = forms.HiddenInput()
#            self.fields['digest_time'].widget = forms.HiddenInput()
#            self.fields['additional_prompt_for_digest'].widget = forms.HiddenInput()
#            self.fields['send_full_article'].widget = forms.HiddenInput()


class OPMLUploadForm(forms.Form):
    # Hint browsers to only allow OPML/XML selection to reduce accidental uploads
    opml_file = forms.FileField(
        label=_("OPML file"),
        widget=forms.ClearableFileInput(
            attrs={
                "accept": "application/xml,text/xml,.opml,.xml",
            }
        ),
    )
