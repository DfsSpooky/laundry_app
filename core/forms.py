from django import forms
from .models import Customer, Order, Category, OrderCategory
from django_select2.forms import Select2Widget

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'email']
        labels = {
            'name': 'Nombre',
            'phone': 'Teléfono',
            'email': 'Correo Electrónico',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full p-2 border rounded'}),
            'phone': forms.TextInput(attrs={'class': 'w-full p-2 border rounded'}),
            'email': forms.EmailInput(attrs={'class': 'w-full p-2 border rounded'}),
        }

class OrderForm(forms.ModelForm):
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all(),
        label='Cliente',
        widget=Select2Widget(attrs={'class': 'w-full p-2 border rounded'}),
        required=True
    )

    class Meta:
        model = Order
        fields = ['customer', 'weight', 'weight_price_per_kg', 'status', 'payment_method', 'payment_status', 'payment_proof', 'partial_amount', 'notes']
        labels = {
            'weight': 'Peso (kg)',
            'weight_price_per_kg': 'Precio por kg',
            'status': 'Estado',
            'payment_method': 'Método de Pago',
            'payment_status': 'Estado de Pago',
            'payment_proof': 'Comprobante de Pago',
            'partial_amount': 'Monto Pagado Parcialmente',
            'notes': 'Notas',
        }
        widgets = {
            'weight': forms.NumberInput(attrs={'class': 'w-full p-2 border rounded', 'step': '0.01'}),
            'weight_price_per_kg': forms.NumberInput(attrs={'class': 'w-full p-2 border rounded', 'step': '0.01'}),
            'status': forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
            'payment_method': forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
            'payment_status': forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
            'payment_proof': forms.FileInput(attrs={'class': 'w-full p-2 border rounded'}),
            'partial_amount': forms.NumberInput(attrs={'class': 'w-full p-2 border rounded', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'w-full p-2 border rounded', 'rows': 4}),
        }

    def clean(self):
        cleaned_data = super().clean()
        payment_method = cleaned_data.get('payment_method')
        payment_proof = cleaned_data.get('payment_proof')
        payment_status = cleaned_data.get('payment_status')
        partial_amount = cleaned_data.get('partial_amount')

        if payment_method in ['YAPE', 'PLIN'] and not payment_proof and not self.instance.payment_proof:
            self.add_error('payment_proof', 'Debes subir un comprobante para pagos con Yape o Plin.')
        if payment_status == 'PARTIAL' and (partial_amount is None or partial_amount <= 0):
            self.add_error('partial_amount', 'Debes ingresar un monto pagado mayor a 0 para pagos parciales.')
        return cleaned_data

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'price', 'description']
        labels = {
            'name': 'Nombre',
            'price': 'Precio',
            'description': 'Descripción',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full p-2 border rounded'}),
            'price': forms.NumberInput(attrs={'class': 'w-full p-2 border rounded', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'w-full p-2 border rounded', 'rows': 4}),
        }

class OrderCategoryForm(forms.ModelForm):
    quantity = forms.IntegerField(min_value=1, label='Cantidad', widget=forms.NumberInput(attrs={'class': 'w-full p-2 border rounded', 'min': '1'}))

    class Meta:
        model = OrderCategory
        fields = ['category', 'quantity']
        labels = {
            'category': 'Categoría',
        }
        widgets = {
            'category': forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
        }

class OrderCategoryInlineForm(forms.Form):
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        label='Categoría',
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded', 'name': 'category'}),
        required=False
    )
    quantity = forms.IntegerField(
        min_value=0,
        initial=0,
        label='Cantidad',
        required=False,
        widget=forms.NumberInput(attrs={'class': 'w-full p-2 border rounded', 'min': '0', 'name': 'quantity'})
    )

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get('category')
        quantity = cleaned_data.get('quantity')
        if quantity > 0 and not category:
            self.add_error('category', 'Selecciona una categoría si especificas una cantidad.')
        return cleaned_data

class CustomerFilterForm(forms.Form):
    search_query = forms.CharField(
        required=False,
        label='Buscar Cliente',
        widget=forms.TextInput(attrs={'class': 'w-full p-2 border rounded', 'placeholder': 'Nombre o código de cliente'})
    )

class OrderFilterForm(forms.Form):
    status = forms.ChoiceField(
        choices=[('', 'Todos')] + Order.STATUS_CHOICES,
        required=False,
        label='Estado del Pedido',
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded'})
    )
    payment_status = forms.ChoiceField(
        choices=[('', 'Todos')] + Order.PAYMENT_STATUS_CHOICES,
        required=False,
        label='Estado de Pago',
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded'})
    )
    date_from = forms.DateField(
        required=False,
        label='Desde',
        widget=forms.DateInput(attrs={'class': 'w-full p-2 border rounded', 'type': 'date'})
    )
    date_to = forms.DateField(
        required=False,
        label='Hasta',
        widget=forms.DateInput(attrs={'class': 'w-full p-2 border rounded', 'type': 'date'})
    )

class ReceiveOrderForm(forms.Form):
    customer_code = forms.CharField(
        label='Código de Cliente',
        required=True,
        widget=forms.TextInput(attrs={'class': 'w-full p-2 border rounded', 'placeholder': 'Ej: 1234', 'id': 'id_customer_code'})
    )
    weight = forms.DecimalField(
        required=False,
        label='Peso (kg)',
        widget=forms.NumberInput(attrs={'class': 'w-full p-2 border rounded', 'step': '0.01'})
    )
    notes = forms.CharField(
        required=False,
        label='Notas',
        widget=forms.Textarea(attrs={'class': 'w-full p-2 border rounded', 'rows': 4})
    )
class ConfigurationForm(forms.Form):
    price_per_kg = forms.DecimalField(
        label='Precio Estándar por Kilo (S/)',
        widget=forms.NumberInput(attrs={'class': 'w-full p-2 border rounded', 'step': '0.01'})
    )