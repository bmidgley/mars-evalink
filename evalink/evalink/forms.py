from django import forms

class ChatForm(forms.Form):
    message = forms.CharField(label="Message", max_length=100)

    def is_valid(self): return True