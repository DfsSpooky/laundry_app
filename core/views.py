from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.forms import formset_factory
from django.http import HttpResponse, JsonResponse
from .models import Customer, Order, Category, OrderCategory, AppConfiguration
from .forms import CustomerForm, OrderForm, CategoryForm, OrderCategoryInlineForm, CustomerFilterForm, OrderFilterForm, ReceiveOrderForm, ConfigurationForm
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from io import BytesIO
from decimal import Decimal
import os



def home(request):
    return render(request, 'core/home.html')

@login_required
def dashboard(request):
    customer_filter_form = CustomerFilterForm(request.GET)
    order_filter_form = OrderFilterForm(request.GET)

    customers = Customer.objects.all()
    if customer_filter_form.is_valid():
        search_query = customer_filter_form.cleaned_data.get('search_query')
        if search_query:
            customers = customers.filter(
                Q(name__icontains=search_query) | Q(customer_code__icontains=search_query)
            )

    orders = Order.objects.all()
    if order_filter_form.is_valid():
        status = order_filter_form.cleaned_data.get('status')
        payment_status = order_filter_form.cleaned_data.get('payment_status')
        date_from = order_filter_form.cleaned_data.get('date_from')
        date_to = order_filter_form.cleaned_data.get('date_to')

        if status:
            orders = orders.filter(status=status)
        if payment_status:
            orders = orders.filter(payment_status=payment_status)
        if date_from:
            orders = orders.filter(created_at__date__gte=date_from)
        if date_to:
            orders = orders.filter(created_at__date__lte=date_to)

    today = datetime.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    daily_income = sum(order.total_price() for order in Order.objects.filter(created_at__date=today, payment_status='PAID'))
    weekly_income = sum(order.total_price() for order in Order.objects.filter(created_at__date__gte=week_ago, payment_status='PAID'))
    monthly_income = sum(order.total_price() for order in Order.objects.filter(created_at__date__gte=month_ago, payment_status='PAID'))

    orders_paginator = Paginator(orders.order_by('-created_at'), 10)
    orders_page_number = request.GET.get('orders_page')
    orders_page = orders_paginator.get_page(orders_page_number)

    customers_paginator = Paginator(customers.order_by('name'), 10)
    customers_page_number = request.GET.get('customers_page')
    customers_page = customers_paginator.get_page(customers_page_number)

    return render(request, 'core/dashboard.html', {
        'orders': orders_page,
        'customers': customers_page,
        'daily_income': daily_income,
        'weekly_income': weekly_income,
        'monthly_income': monthly_income,
        'customer_filter_form': customer_filter_form,
        'order_filter_form': order_filter_form,
    })

@login_required
def add_customer(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            messages.success(request, f'Cliente {customer.name} agregado correctamente con código {customer.customer_code}.')
            return redirect('dashboard')
    else:
        form = CustomerForm()
    return render(request, 'core/add_customer.html', {'form': form})

@login_required
def add_category(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Categoría agregada correctamente.')
            return redirect('dashboard')
    else:
        form = CategoryForm()
    return render(request, 'core/add_category.html', {'form': form})

@login_required
def add_order(request):
    OrderCategoryFormSet = formset_factory(OrderCategoryInlineForm, extra=1, can_delete=True)
    if request.method == 'POST':
        order_form = OrderForm(request.POST, request.FILES)
        formset = OrderCategoryFormSet(request.POST)
        if order_form.is_valid() and formset.is_valid():
            order = order_form.save()
            for form in formset:
                if not form.cleaned_data.get('DELETE', False):
                    quantity = form.cleaned_data.get('quantity', 0)
                    category = form.cleaned_data.get('category')
                    if quantity > 0 and category:
                        OrderCategory.objects.create(
                            order=order,
                            category=category,
                            quantity=quantity
                        )
            order.generate_qr_code()
            messages.success(request, 'Pedido creado correctamente.')
            return redirect('dashboard')
        else:
            messages.error(request, f'Error en el formulario: {order_form.errors} {formset.errors}')
    else:
        order_form = OrderForm()
        formset = OrderCategoryFormSet()
    return render(request, 'core/add_order.html', {'order_form': order_form, 'formset': formset})

def order_status(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    return render(request, 'core/order_status.html', {'order': order})

@login_required
def update_order_status(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST':
        order.status = 'READY'
        order.save()
        messages.success(request, f'Pedido {order.id} marcado como listo para recoger.')
        return redirect('dashboard')
    return redirect('dashboard')

@login_required
def update_payment_status(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST':
        payment_status = request.POST.get('payment_status')
        partial_amount = request.POST.get('partial_amount')
        payment_proof = request.FILES.get('payment_proof')
        if payment_status in ['PENDING', 'PAID', 'PARTIAL']:
            order.payment_status = payment_status
            if payment_status == 'PARTIAL' and partial_amount:
                try:
                    order.partial_amount = float(partial_amount)
                except ValueError:
                    messages.error(request, 'Monto parcial inválido.')
                    return redirect('dashboard')
            if payment_proof:
                order.payment_proof = payment_proof
            order.save()
            messages.success(request, f'Estado de pago del pedido {order.id} actualizado correctamente.')
        else:
            messages.error(request, 'Estado de pago inválido.')
        return redirect('dashboard')
    return redirect('dashboard')

@login_required
def manage_customer_orders(request, customer_code):
    customer = get_object_or_404(Customer, customer_code=customer_code)
    orders = Order.objects.filter(customer=customer).order_by('-created_at')

    # --- INICIO DE LA LÓGICA AÑADIDA ---
    # Calculamos la deuda total sumando los montos restantes de cada pedido de este cliente
    customer_total_due = sum(order.remaining_amount() for order in orders)
    # --- FIN DE LA LÓGICA AÑADIDA ---

    # Creamos el contexto y añadimos la nueva variable
    context = {
        'customer': customer, 
        'orders': orders,
        'customer_total_due': customer_total_due, # <-- La nueva variable que necesita el HTML
    }
    
    return render(request, 'core/manage_customer_orders.html', context)

def customer_status(request, customer_code):
    customer = get_object_or_404(Customer, customer_code=customer_code)
    orders = Order.objects.filter(customer=customer).order_by('-created_at')
    return render(request, 'core/customer_status.html', {'customer': customer, 'orders': orders})

@login_required
def edit_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    OrderCategoryFormSet = formset_factory(OrderCategoryInlineForm, extra=1, can_delete=True)
    if request.method == 'POST':
        order_form = OrderForm(request.POST, request.FILES, instance=order)
        formset = OrderCategoryFormSet(request.POST)
        if order_form.is_valid() and formset.is_valid():
            order_form.save()
            OrderCategory.objects.filter(order=order).delete()
            for form in formset:
                if not form.cleaned_data.get('DELETE', False):
                    quantity = form.cleaned_data.get('quantity', 0)
                    category = form.cleaned_data.get('category')
                    if quantity > 0 and category:
                        OrderCategory.objects.create(
                            order=order,
                            category=category,
                            quantity=quantity
                        )
            order.generate_qr_code()
            messages.success(request, f'Pedido {order.id} actualizado correctamente.')
            return redirect('manage_customer_orders', customer_code=order.customer.customer_code)
    else:
        order_form = OrderForm(instance=order)
        initial_data = [
            {'category': oc.category, 'quantity': oc.quantity}
            for oc in OrderCategory.objects.filter(order=order)
        ]
        all_categories = Category.objects.all()
        for category in all_categories:
            if not any(item['category'] == category for item in initial_data):
                initial_data.append({'category': category, 'quantity': 0})
        formset = OrderCategoryFormSet(initial=initial_data)
    return render(request, 'core/edit_order.html', {'order_form': order_form, 'formset': formset, 'order': order})

@login_required
@login_required
def receive_order(request):
    customer = None
    form = ReceiveOrderForm(request.POST or None)

    # Lógica para el POST (cuando se envía el formulario)
    if request.method == 'POST':
        action = request.POST.get('action')
        
        # --- ACCIÓN 1: BUSCAR CLIENTE ---
        if action == 'search':
            if form.is_valid():
                customer_code = form.cleaned_data.get('customer_code')
                try:
                    customer = Customer.objects.get(customer_code=customer_code)
                    # Ya no necesitamos preparar ningún formset aquí
                except Customer.DoesNotExist:
                    messages.error(request, f"El cliente con el código '{customer_code}' no fue encontrado.")
            else:
                 messages.error(request, 'Por favor, ingresa un código de cliente válido.')

        # --- ACCIÓN 2: CONFIRMAR Y CREAR PEDIDO ---
        elif action == 'confirm':
            customer_id = request.POST.get('customer_id')
            customer = get_object_or_404(Customer, id=customer_id)

            if form.is_valid():
                weight = form.cleaned_data.get('weight')
                
                # La nueva validación: el pedido debe tener un peso para ser creado
                if weight is None or weight <= 0:
                    messages.error(request, "Para crear el pedido, debes ingresar un peso mayor a cero.")
                else:
                    price_setting = AppConfiguration.objects.get(key='default_price_per_kg')
                    order = Order.objects.create(
                        customer=customer,
                        weight=weight,
                        # --- LÍNEA MODIFICADA ---
                        weight_price_per_kg=Decimal(price_setting.value),
                        notes=form.cleaned_data.get('notes'),
                        status='PROCESSING'
                    )
                    
                    # Se eliminó el bucle que creaba OrderCategory
                    
                    order.generate_qr_code()
                    messages.success(request, f'Pedido #{order.id} por peso creado exitosamente para {customer.name}.')
                    return redirect('manage_customer_orders', customer_code=customer.customer_code)
            else:
                messages.error(request, 'Error en el formulario. Por favor, revisa los datos ingresados.')
    
    # Lógica para el GET (cuando se carga la página por primera vez)
    else:
        form = ReceiveOrderForm()

    # Renderizar la plantilla (ya no se pasa el formset)
    context = {
        'form': form,
        'customer': customer
    }
    return render(request, 'core/receive_order.html', context)

@login_required
def download_order_pdf(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesizes=letter,
                            rightMargin=0.75 * inch, leftMargin=0.75 * inch,
                            topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    elements = []

    # --- Modern Color Palette & Fonts ---
    # Using a slightly darker primary color for a more corporate feel
    primary_color = colors.HexColor('#1A73E8') # A common blue in modern tech UIs
    secondary_color = colors.HexColor('#E8F0FE') # Very light blue for subtle backgrounds
    text_dark = colors.HexColor('#202124') # Near black for primary text
    text_medium = colors.HexColor('#5F6368') # Dark grey for secondary text/labels
    border_light = colors.HexColor('#DADCE0') # Light grey for subtle borders

    # Custom Paragraph Styles
    # Company Name (Large and bold)
    company_name_style = ParagraphStyle(
        name='CompanyName',
        fontSize=30, # Even larger for impact
        leading=36,
        textColor=primary_color,
        alignment=0,
        fontName='Helvetica-Bold' # Helvetica or Arial are clean, common choices
    )
    # Company Address/Contact Info
    company_info_style = ParagraphStyle(
        name='CompanyInfo',
        fontSize=9,
        leading=11,
        textColor=text_medium,
        alignment=0,
        fontName='Helvetica'
    )
    # Section Title (e.g., "Invoice Details", "Bill To")
    section_title_style = ParagraphStyle(
        name='SectionTitle',
        fontSize=12,
        leading=14,
        textColor=text_dark,
        alignment=0,
        fontName='Helvetica-Bold'
    )
    # Key Value Label (e.g., "Invoice #:", "Date:")
    label_style = ParagraphStyle(
        name='Label',
        fontSize=10,
        leading=12,
        textColor=text_medium,
        alignment=0,
        fontName='Helvetica'
    )
    # Key Value Data (e.g., "INV-001", "2023-10-26")
    data_style = ParagraphStyle(
        name='Data',
        fontSize=10,
        leading=12,
        textColor=text_dark,
        alignment=0,
        fontName='Helvetica-Bold'
    )
    # Item Table Header
    table_header_style = ParagraphStyle(
        name='TableHeader',
        fontSize=10,
        leading=12,
        textColor=text_dark,
        alignment=1, # Center alignment
        fontName='Helvetica-Bold'
    )
    # Item Table Cell
    table_cell_style = ParagraphStyle(
        name='TableCell',
        fontSize=9,
        leading=11,
        textColor=text_dark,
        alignment=1, # Center alignment
        fontName='Helvetica'
    )
    # Right-aligned Table Cell (for prices)
    table_cell_right_style = ParagraphStyle(
        name='TableCellRight',
        fontSize=9,
        leading=11,
        textColor=text_dark,
        alignment=2, # Right alignment
        fontName='Helvetica'
    )
    # Subtotal/Tax/Total Labels (right-aligned)
    summary_label_style = ParagraphStyle(
        name='SummaryLabel',
        fontSize=11,
        leading=13,
        textColor=text_dark,
        alignment=2, # Right alignment
        fontName='Helvetica'
    )
    # Grand Total Value (larger, bold, primary color)
    grand_total_value_style = ParagraphStyle(
        name='GrandTotalValue',
        fontSize=18,
        leading=22,
        textColor=primary_color,
        alignment=2, # Right alignment
        fontName='Helvetica-Bold'
    )
    # Footer Text
    footer_style = ParagraphStyle(
        name='Footer',
        fontSize=9,
        leading=11,
        textColor=text_medium,
        alignment=1, # Center alignment
        fontName='Helvetica'
    )

    # --- Header Section: Company Name & Info ---
    elements.append(Paragraph("<b>LAVANDERÍA MODERNA</b>", company_name_style))
    elements.append(Paragraph("Calle Ficticia 123, Lima, Perú | +51 987 654 321 | info@lavanderiamoderna.com", company_info_style))
    elements.append(Spacer(1, 0.5 * inch)) # More space after header

    # --- Invoice Details & Bill To (Side-by-Side Clean Layout) ---
    # Invoice Details
    invoice_details_data = [
        [Paragraph("<b>RECIBO #:</b>", label_style), Paragraph(f"{order.id}", data_style)],
        [Paragraph("<b>EMITIDO:</b>", label_style), Paragraph(datetime.now().strftime('%d/%m/%Y'), data_style)],
        [Paragraph("<b>VENCIMIENTO:</b>", label_style), Paragraph((datetime.now() + timedelta(days=7)).strftime('%d/%m/%Y'), data_style)],
    ]
    invoice_details_table = Table(invoice_details_data, colWidths=[1.5 * inch, 2.0 * inch])
    invoice_details_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('GRID', (0,0), (-1,-1), 0.25, border_light), # Light borders for definition
        ('BACKGROUND', (0,0), (-1,-1), secondary_color),
    ]))

    # Bill To
    bill_to_data = [
        [Paragraph("<b>DESTINATARIO:</b>", section_title_style)],
        [Paragraph(f"{order.customer.name}", data_style)],
        [Paragraph(f"Código: {order.customer.customer_code}", label_style)],
    ]
    if order.customer.phone:
        bill_to_data.append([Paragraph(f"Teléfono: {order.customer.phone}", label_style)])
    if order.customer.email:
        bill_to_data.append([Paragraph(f"Correo: {order.customer.email}", label_style)])

    bill_to_table = Table(bill_to_data, colWidths=[3.0 * inch])
    bill_to_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))

    # Combine into a single table for two-column layout
    # Use nested tables for precise control
    combined_info = Table([[invoice_details_table, Spacer(1,1), bill_to_table]], colWidths=[3.5 * inch, 0.5 * inch, 3.0 * inch])
    combined_info.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    elements.append(combined_info)
    elements.append(Spacer(1, 0.4 * inch))

    # --- Line Items Table ---
    elements.append(Paragraph("<b>DETALLES DEL SERVICIO</b>", section_title_style))
    elements.append(Spacer(1, 0.15 * inch))

    item_table_data = [
        [Paragraph('PRODUCTO/SERVICIO', table_header_style),
         Paragraph('DESCRIPCIÓN', table_header_style),
         Paragraph('CANT.', table_header_style),
         Paragraph('PRECIO UNIT. (S/)', table_header_style),
         Paragraph('TOTAL (S/)', table_header_style)]
    ]
    total = Decimal('0.00')
    for oc in order.ordercategory_set.all():
        item_total = oc.quantity * oc.category.price
        total += item_total
        item_table_data.append([
            Paragraph(oc.category.name, table_cell_style),
            Paragraph(oc.category.description or 'Lavado estándar', table_cell_style),
            Paragraph(str(oc.quantity), table_cell_style),
            Paragraph(f"{oc.category.price:.2f}", table_cell_right_style),
            Paragraph(f"{item_total:.2f}", table_cell_right_style)
        ])
    if order.weight and order.weight_price_per_kg:
        weight_total = order.weight * order.weight_price_per_kg
        total += weight_total
        item_table_data.append([
            Paragraph(f"Peso ({order.weight} kg)", table_cell_style),
            Paragraph('Lavado por peso', table_cell_style),
            Paragraph('1', table_cell_style),
            Paragraph(f"{order.weight_price_per_kg:.2f}", table_cell_right_style),
            Paragraph(f"{weight_total:.2f}", table_cell_right_style)
        ])

    item_table = Table(item_table_data, colWidths=[1.5 * inch, 2.0 * inch, 0.8 * inch, 1.2 * inch, 1.2 * inch])
    item_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), secondary_color), # Light blue header background
        ('TEXTCOLOR', (0, 0), (-1, 0), text_dark),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),

        ('GRID', (0, 0), (-1, -1), 0.5, border_light), # All cells have light borders
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0,1), (-1,-1), 6),
        ('RIGHTPADDING', (0,1), (-1,-1), 6),
        ('TOPPADDING', (0,1), (-1,-1), 6),
        ('BOTTOMPADDING', (0,1), (-1,-1), 6),
    ]))
    elements.append(item_table)
    elements.append(Spacer(1, 0.4 * inch))

    # --- Financial Summary (Right-aligned and prominent total) ---
    tax_rate = Decimal('0.13')
    tax = total * tax_rate
    grand_total = total + tax

    summary_data = [
        [Paragraph('Subtotal:', summary_label_style), Paragraph(f'S/{total:.2f}', data_style)],
        [Paragraph('Impuesto (13%):', summary_label_style), Paragraph(f'S/{tax:.2f}', data_style)],
        [Paragraph('TOTAL:', grand_total_value_style), Paragraph(f'S/{grand_total:.2f}', grand_total_value_style)]
    ]
    summary_table = Table(summary_data, colWidths=[5.0 * inch, 1.75 * inch]) # Wider first column for labels
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LINEABOVE', (0, -1), (-1, -1), 1, border_light), # Line above grand total
        ('LINEBELOW', (0, -1), (-1, -1), 2, primary_color), # Thicker line below grand total
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.5 * inch))

    # --- Footer Section: Message and QR Code ---
    footer_elements = []
    footer_elements.append(Paragraph("Gracias por tu preferencia. ¡Vuelve pronto!", footer_style))
    footer_elements.append(Spacer(1, 0.2 * inch))

    if order.qr_code and os.path.exists(order.qr_code.path):
        qr_image = Image(order.qr_code.path, 1.2 * inch, 1.2 * inch) # Slightly larger QR for readability
        qr_image.hAlign = 'CENTER'
        footer_elements.append(qr_image)

    footer_table = Table([[elem] for elem in footer_elements], colWidths=[letter[0] - 1.5*inch]) # Match document margins
    footer_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(footer_table)

    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=recibo_pedido_{order.id}.pdf'
    response.write(buffer.getvalue())
    buffer.close()
    return response

@login_required
def payment_audit(request):
    orders = Order.objects.filter(payment_status__in=['PENDING', 'PARTIAL']).order_by('-created_at')
    paginator = Paginator(orders, 10)
    page_number = request.GET.get('page')
    page = paginator.get_page(page_number)
    return render(request, 'core/payment_audit.html', {'orders': page})

@login_required
def cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST' and order.status != 'CANCELLED':
        order.status = 'CANCELLED'
        order.save()
        messages.success(request, f'Pedido {order.id} anulado correctamente.')
    return redirect('manage_customer_orders', customer_code=order.customer.customer_code)

@login_required
def search_customers(request):
    query = request.GET.get('query', '')
    customers = Customer.objects.filter(
        Q(name__icontains=query) | Q(customer_code__icontains=query)
    )[:10]
    results = [
        {'id': customer.id, 'name': customer.name, 'code': customer.customer_code}
        for customer in customers
    ]
    return JsonResponse({'results': results})
@login_required
def manage_settings(request):
    # Usamos update_or_create para manejar el caso de que el ajuste no exista aún
    price_setting, created = AppConfiguration.objects.get_or_create(
        key='default_price_per_kg',
        defaults={'value': '5.00'} # Valor inicial si no existe
    )

    if request.method == 'POST':
        form = ConfigurationForm(request.POST)
        if form.is_valid():
            price_setting.value = str(form.cleaned_data['price_per_kg'])
            price_setting.save()
            messages.success(request, 'El precio por kilo ha sido actualizado correctamente.')
            return redirect('manage_settings')
    else:
        # Al cargar, mostramos el valor guardado
        form = ConfigurationForm(initial={'price_per_kg': Decimal(price_setting.value)})

    return render(request, 'core/settings.html', {'form': form})
@login_required
def mark_order_as_delivered(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST':
        # Validación: No entregar si aún hay deuda
        if order.remaining_amount() > 0:
            messages.error(request, f'Error: El pedido #{order.id} no puede ser entregado porque tiene una deuda pendiente de S/ {order.remaining_amount()}.')
        else:
            order.status = 'DELIVERED'
            order.save()
            messages.success(request, f'Pedido #{order.id} marcado como ENTREGADO correctamente.')
        
        # Redirigir de vuelta a la página de donde vino
        return redirect('manage_customer_orders', customer_code=order.customer.customer_code)
    
    # Si no es POST, simplemente redirigir
    return redirect('dashboard')