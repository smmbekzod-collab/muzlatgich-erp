"""READ-ONLY STAGING audit of warehouse movement and settlement history.

Nothing gets inserted, saved, queued, notified, or altered. Strict TEST org
guard and PostgreSQL SET TRANSACTION READ ONLY. JSON stdout excludes secrets.
"""
import json
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Count, Sum
from django.utils import timezone

from core.models import Organization
from warehouse.models import Lot, Operation, CameraRentalInvoice, CameraRentalPayment
from warehouse.services import totals, pending
from warehouse.management.commands.seed_staging_demo import must_be_staging


def money(value):
    return str(value if value is not None else Decimal('0'))


def clock(timestamp):
    return timezone.localtime(timestamp, ZoneInfo('Asia/Tashkent')).strftime('%Y-%m-%d %H:%M:%S')


class Command(BaseCommand):
    help = 'STAGING TEST only: read committed operation history and reconcile physical stock/payment/debt.'

    def handle(self, *args, **opts):
        must_be_staging()
        if connection.vendor != 'postgresql':
            raise CommandError('PostgreSQL STAGING baza talab qilinadi.')
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION READ ONLY')
            org = Organization.objects.filter(code='test-agrostar-holadelnik').first()
            if org is None or not org.name.startswith('TEST'):
                raise CommandError('Belgilangan test tashkiloti topilmadi.')

            lots = list(Lot.objects.filter(organization=org)
                .select_related('customer','camera','camera__facility')
                .order_by('created_at','pk'))
            all_ops = list(Operation.objects.filter(lot__organization=org)
                .select_related('lot','lot__customer','camera')
                .order_by('created_at','pk'))
            by_lot = {}
            for op in all_ops:
                by_lot.setdefault(op.lot_id, []).append(op)

            anomalies = []
            summaries = []
            for lot in lots:
                history = by_lot.get(lot.pk, [])
                reversed_ids = {op.reversal_of_id for op in history if op.reversal_of_id is not None}
                effective = [op for op in history
                    if op.kind in ('dispatch','loss') and op.pk not in reversed_ids]
                expected_boxes = lot.initial_boxes - sum(op.boxes for op in effective)
                expected_gross = lot.initial_gross - sum((op.gross for op in effective),Decimal('0'))
                expected_tare = lot.initial_tare - sum((op.tare for op in effective),Decimal('0'))
                actual = (lot.boxes, lot.gross, lot.tare)
                expected = (expected_boxes, expected_gross, expected_tare)
                matches = expected == actual
                if not matches:
                    anomalies.append(f'STOCK_MISMATCH {lot.short_id}: expected={expected} actual={actual}')
                last = history[-1] if history else None
                if last and (
                    last.boxes_after != lot.boxes or
                    last.gross_after != lot.gross or
                    last.tare_after != lot.tare
                ):
                    anomalies.append(f'LAST_OPERATION_SNAPSHOT_MISMATCH {lot.short_id}')
                summary=totals(lot)
                if summary['charged'] != sum((op.charge for op in history),Decimal('0')):
                    anomalies.append(f'CHARGE_LEDGER_MISMATCH {lot.short_id}')
                if summary['paid'] != sum((op.payment for op in history),Decimal('0')):
                    anomalies.append(f'PAYMENT_LEDGER_MISMATCH {lot.short_id}')
                summaries.append({
                    'lot':lot.short_id,
                    'customer':lot.customer.name,
                    'camera':f'{lot.camera.facility.name} / {lot.camera.number}',
                    'product':lot.product,
                    'original_boxes':lot.initial_boxes,
                    'dispatched_boxes':sum(op.boxes for op in effective if op.kind=='dispatch'),
                    'lost_boxes':sum(op.boxes for op in effective if op.kind=='loss'),
                    'remaining_boxes':lot.boxes,
                    'remaining_net_kg':money(lot.net),
                    'charged_uzs':money(summary['charged']),
                    'paid_uzs':money(summary['paid']),
                    'recorded_debt_uzs':money(summary['debt']),
                    'unbilled_estimate_uzs':money(pending(lot)),
                    'latest_operation_at':clock(last.created_at) if last else None,
                    'stock_reconciles':matches,
                })
            invoices = list(CameraRentalInvoice.objects.filter(
                agreement__camera__organization=org).select_related(
                'agreement','agreement__customer'))
            rentals = [{
                'invoice_id':invoice.pk,
                'customer':invoice.agreement.customer.name,
                'amount_uzs':money(invoice.amount),
                'paid_uzs':money(invoice.paid),
                'debt_uzs':money(invoice.debt)
            } for invoice in invoices]
            recent_operations = [{
                'time':clock(op.created_at),
                'kind':op.kind,
                'lot':op.lot.short_id,
                'customer':op.lot.customer.name,
                'camera':op.camera.number,
                'boxes_changed':op.boxes,
                'net_kg_changed':money(op.net),
                'boxes_after':op.boxes_after,
                'net_kg_after':money(op.gross_after-op.tare_after),
                'charge_uzs':money(op.charge),
                'payment_uzs':money(op.payment),
                'payment_method':op.payment_method,
                'reversal_of':op.reversal_of.short_id if op.reversal_of_id else None,
            } for op in reversed(all_ops[-25:])]

            time_cutoff = datetime(2026,10,11,8,0,tzinfo=ZoneInfo('Asia/Tashkent'))
            new_ops = [op for op in all_ops if op.created_at >= time_cutoff]
            active = [lot for lot in lots if lot.closed_on is None]
            report = {
                'checked_at':clock(timezone.now()),
                'organization':org.name,
                'total_lots':len(lots),
                'total_operations':len(all_ops),
                'operations_since_11_oct_08':len(new_ops),
                'operations_since_11_oct_08_kinds':[
                    {'kind':name,'count':sum(op.kind==name for op in new_ops)}
                    for name in ('receive','dispatch','payment','loss','transfer','storage_bill','reversal')
                    if any(op.kind==name for op in new_ops)
                ],
                'active_stock_boxes':sum(lot.boxes for lot in active),
                'active_stock_net_kg':money(sum((lot.net for lot in active),Decimal('0'))),
                'lots':summaries,
                'rental_invoices':rentals,
                'rental_total_debt_uzs':money(sum((invoice.debt for invoice in invoices),Decimal('0'))),
                'last_25_operations':recent_operations,
                'anomalies':anomalies,
                'all_read_only':True,
            }
            self.stdout.write('STAGING_HISTORY_AUDIT '+json.dumps(report,ensure_ascii=False,default=str))
