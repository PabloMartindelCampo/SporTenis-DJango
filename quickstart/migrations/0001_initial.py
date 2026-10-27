import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Categoria',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=60, unique=True)),
                ('descripcion', models.TextField(blank=True)),
            ],
            options={
                'verbose_name_plural': 'categorías',
                'ordering': ['nombre'],
            },
        ),
        migrations.CreateModel(
            name='Inventario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('talla', models.DecimalField(decimal_places=1, max_digits=3, validators=[django.core.validators.MinValueValidator(Decimal('12')), django.core.validators.MaxValueValidator(Decimal('35'))])),
                ('cantidad', models.PositiveIntegerField(default=0)),
                ('stock_minimo', models.PositiveIntegerField(default=2)),
            ],
            options={
                'verbose_name_plural': 'inventario',
                'ordering': ['tenis', 'talla'],
            },
        ),
        migrations.CreateModel(
            name='Marca',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=60, unique=True)),
                ('pais_origen', models.CharField(blank=True, max_length=60)),
                ('logo', models.ImageField(blank=True, null=True, upload_to='marcas/')),
            ],
            options={
                'ordering': ['nombre'],
            },
        ),
        migrations.CreateModel(
            name='MovimientoInventario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[('ENTRADA', 'Entrada'), ('SALIDA', 'Salida'), ('AJUSTE', 'Ajuste')], max_length=7)),
                ('cantidad', models.PositiveIntegerField()),
                ('stock_anterior', models.PositiveIntegerField()),
                ('stock_resultante', models.PositiveIntegerField()),
                ('motivo', models.CharField(blank=True, max_length=200)),
                ('fecha', models.DateTimeField(auto_now_add=True)),
                ('inventario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='movimientos', to='quickstart.inventario')),
                ('usuario', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='movimientos', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'movimientos de inventario',
                'ordering': ['-fecha'],
            },
        ),
        migrations.CreateModel(
            name='Tenis',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sku', models.CharField(max_length=20, unique=True, verbose_name='SKU')),
                ('nombre', models.CharField(max_length=100)),
                ('descripcion', models.TextField(blank=True)),
                ('color', models.CharField(max_length=40)),
                ('genero', models.CharField(choices=[('H', 'Hombre'), ('M', 'Mujer'), ('U', 'Unisex'), ('N', 'Niño')], default='U', max_length=1)),
                ('precio', models.DecimalField(decimal_places=2, max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('precio_oferta', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ('imagen', models.ImageField(blank=True, null=True, upload_to='tenis/')),
                ('estado', models.CharField(choices=[('ACTIVO', 'Activo'), ('DESCONTINUADO', 'Descontinuado')], default='ACTIVO', max_length=15)),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('actualizado', models.DateTimeField(auto_now=True)),
                ('categorias', models.ManyToManyField(blank=True, related_name='tenis', to='quickstart.categoria')),
                ('favoritos', models.ManyToManyField(blank=True, related_name='tenis_favoritos', to=settings.AUTH_USER_MODEL)),
                ('marca', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='tenis', to='quickstart.marca')),
            ],
            options={
                'verbose_name_plural': 'tenis',
                'ordering': ['-creado'],
            },
        ),
        migrations.AddField(
            model_name='inventario',
            name='tenis',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inventario', to='quickstart.tenis'),
        ),
        migrations.AddConstraint(
            model_name='inventario',
            constraint=models.UniqueConstraint(fields=('tenis', 'talla'), name='unique_tenis_talla'),
        ),
    ]
