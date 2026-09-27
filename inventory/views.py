import io
import qrcode
from datetime import timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, Http404
from django.db import transaction
from django.utils import timezone

from .models import Product, InventoryHistory, RestockSchedule
from .forms import ProductCreateForm, ProductEditForm


def home(request):
    """ホーム画面: 有効な商品の一覧、現在庫数、補充予定情報、管理画面へのリンク"""
    products = Product.objects.filter(is_active=True).prefetch_related("restock_schedules")
    
    product_list = []
    for p in products:
        unprocessed_schedules = [s for s in p.restock_schedules.all() if not s.processed]
        product_list.append({
            "product": p,
            "pending_restocks": unprocessed_schedules,
            "next_restock": unprocessed_schedules[0] if unprocessed_schedules else None,
        })

    return render(request, "inventory/home.html", {"product_list": product_list})


def product_detail(request, pk):
    """商品詳細画面"""
    product = get_object_or_404(Product, pk=pk)
    histories = product.inventory_histories.all()[:20]
    pending_schedules = product.restock_schedules.filter(processed=False)
    next_restock = pending_schedules.first()
    total_pending_quantity = sum(s.quantity for s in pending_schedules)

    return render(request, "inventory/product_detail.html", {
        "product": product,
        "histories": histories,
        "pending_schedules": pending_schedules,
        "next_restock": next_restock,
        "total_pending_quantity": total_pending_quantity,
    })


def qr_process(request, qr_token):
    """QR処理画面"""
    product = Product.objects.filter(qr_token=qr_token).first()
    if not product:
        return render(request, "inventory/qr_error.html", {"message": "指定された商品が見つかりません。"}, status=404)
    
    if not product.is_active:
        return render(request, "inventory/qr_error.html", {"message": "この商品は現在使用できません。"}, status=400)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "use":
            with transaction.atomic():
                # Lock row for transaction consistency
                p = Product.objects.select_for_update().get(id=product.id)
                if p.stock <= 0:
                    return render(request, "inventory/qr_out_of_stock.html", {"product": p})
                
                # In-stock processing:
                p.stock -= 1
                p.save(update_fields=["stock", "updated_at"])

                # Log history
                InventoryHistory.objects.create(
                    product=p,
                    change_type=InventoryHistory.ChangeType.USE,
                    quantity=-1,
                )

                # Schedule restock in 3 days
                scheduled_time = timezone.now() + timedelta(days=3)
                RestockSchedule.objects.create(
                    product=p,
                    quantity=1,
                    scheduled_at=scheduled_time,
                )

                # If stock reached 0
                if p.stock == 0:
                    return render(request, "inventory/qr_stock_zero_result.html", {
                        "product": p,
                        "scheduled_at": scheduled_time,
                    })
                else:
                    return render(request, "inventory/qr_use_success.html", {"product": p})

        elif action == "cancel":
            return redirect("home")

    return render(request, "inventory/qr_confirm.html", {"product": product})


# --- カスタム管理画面 Views ---

def manage_product_list(request):
    """管理画面: 商品一覧"""
    products = Product.objects.all()
    return render(request, "inventory/manage_product_list.html", {"products": products})


def manage_product_create(request):
    """商品登録画面"""
    if request.method == "POST":
        form = ProductCreateForm(request.POST)
        if form.is_valid():
            product = form.save()
            # Initial stock history if stock > 0
            if product.stock > 0:
                InventoryHistory.objects.create(
                    product=product,
                    change_type=InventoryHistory.ChangeType.ADJUST,
                    quantity=product.stock,
                )
            return redirect("manage_product_qr", pk=product.pk)
    else:
        form = ProductCreateForm()

    return render(request, "inventory/manage_product_form.html", {
        "form": form,
        "title": "商品登録",
        "btn_label": "登録してQRコードを表示",
    })


def manage_product_edit(request, pk):
    """商品編集画面"""
    product = get_object_or_404(Product, pk=pk)
    old_stock = product.stock

    if request.method == "POST":
        form = ProductEditForm(request.POST, instance=product)
        if form.is_valid():
            updated_product = form.save()
            new_stock = updated_product.stock
            stock_diff = new_stock - old_stock
            if stock_diff != 0:
                InventoryHistory.objects.create(
                    product=updated_product,
                    change_type=InventoryHistory.ChangeType.ADJUST,
                    quantity=stock_diff,
                )
            return redirect("manage_product_list")
    else:
        form = ProductEditForm(instance=product)

    return render(request, "inventory/manage_product_form.html", {
        "form": form,
        "product": product,
        "title": "商品編集",
        "btn_label": "保存",
    })


def manage_product_qr(request, pk):
    """QRコード表示画面"""
    product = get_object_or_404(Product, pk=pk)
    qr_url = request.build_absolute_uri(f"/q/{product.qr_token}")
    return render(request, "inventory/manage_product_qr.html", {
        "product": product,
        "qr_url": qr_url,
    })


def generate_qr_image(request, qr_token):
    """QRコード画像（PNG）を動的に生成して返すビュー"""
    product = get_object_or_404(Product, qr_token=qr_token)
    qr_url = request.build_absolute_uri(f"/q/{product.qr_token}")

    img = qrcode.make(qr_url)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return HttpResponse(buffer.getvalue(), content_type="image/png")
