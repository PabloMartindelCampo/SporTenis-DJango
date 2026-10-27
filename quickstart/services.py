from django.db import transaction
from rest_framework.exceptions import ValidationError

from .models import Inventario, MovimientoInventario


@transaction.atomic
def registrar_movimiento(inventario, tipo, cantidad, usuario=None, motivo=""):
    inv = Inventario.objects.select_for_update().get(pk=inventario.pk)
    anterior = inv.cantidad

    if tipo == MovimientoInventario.Tipo.ENTRADA:
        nuevo = anterior + cantidad
    elif tipo == MovimientoInventario.Tipo.SALIDA:
        if cantidad > anterior:
            raise ValidationError({
                "cantidad": f"Stock insuficiente: hay {anterior} pares en talla {inv.talla} "
                            f"y se intentan sacar {cantidad}."
            })
        nuevo = anterior - cantidad
    elif tipo == MovimientoInventario.Tipo.AJUSTE:
        nuevo = cantidad
    else:
        raise ValidationError({"tipo": "Tipo de movimiento no válido."})

    inv.cantidad = nuevo
    inv.save(update_fields=["cantidad"])

    return MovimientoInventario.objects.create(
        inventario=inv,
        tipo=tipo,
        cantidad=cantidad,
        stock_anterior=anterior,
        stock_resultante=nuevo,
        motivo=motivo,
        usuario=usuario,
    )
