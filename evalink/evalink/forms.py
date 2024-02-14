from django import forms

class ChatForm(forms.Form):
    message = forms.CharField(label="Message", max_length=100)