import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/l10n/app_strings.dart';
import '../../../core/models/auth_models.dart';
import '../../../core/providers.dart';
import '../../../core/utils/formatters.dart';
import '../../../shared/widgets/async_view.dart';
import '../../../shared/widgets/charts.dart';
import '../../../shared/widgets/page_header.dart';
import '../../../shared/widgets/status_chip.dart';

/// Role aware dashboard: the API returns the cards the user is allowed to see
/// (`/dashboards/me`), plus the trend charts and the document lists below.
final dashboardProvider = FutureProvider.autoDispose<Map<String, dynamic>>(
  (Ref ref) => ref.watch(apiProvider).object('/dashboards/me'),
);

final salesTrendProvider = FutureProvider.autoDispose<List<Map<String, dynamic>>>(
  (Ref ref) => ref.watch(apiProvider).collection('/dashboards/charts/sales-trend'),
);

final topProductsProvider = FutureProvider.autoDispose<List<Map<String, dynamic>>>(
  (Ref ref) => ref.watch(apiProvider).collection('/dashboards/charts/top-products'),
);

class DashboardPage extends ConsumerWidget {
  const DashboardPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AuthState auth = ref.watch(authProvider);
    final String locale = Localizations.localeOf(context).languageCode;
    final String currency = auth.company?.baseCurrencyCode ?? '';

    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(dashboardProvider);
        ref.invalidate(salesTrendProvider);
        ref.invalidate(topProductsProvider);
      },
      child: ListView(
        padding: const EdgeInsets.only(bottom: 32),
        children: <Widget>[
          PageHeader(
            titleKey: 'dash.title',
            subtitle: context.trp('dash.welcome', <String, Object>{'name': auth.user?.displayName ?? ''}),
            breadcrumbs: <String>['nav.dashboard'],
            actions: <Widget>[
              OutlinedButton.icon(
                onPressed: () {
                  ref.invalidate(dashboardProvider);
                  ref.invalidate(salesTrendProvider);
                  ref.invalidate(topProductsProvider);
                },
                icon: const Icon(Icons.refresh, size: 18),
                label: Text(context.tr('common.refresh')),
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: AsyncView<Map<String, dynamic>>(
              value: ref.watch(dashboardProvider),
              onRetry: () => ref.invalidate(dashboardProvider),
              builder: (Map<String, dynamic> data) => Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  _KpiGrid(data: data, locale: locale, currency: currency),
                  const SizedBox(height: 16),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Expanded(
                        flex: 3,
                        child: SectionCard(
                          titleKey: 'dash.sales_trend',
                          child: AsyncView<List<Map<String, dynamic>>>(
                            value: ref.watch(salesTrendProvider),
                            builder: (List<Map<String, dynamic>> rows) => SimpleLineChart(
                              labels: rows.map((Map<String, dynamic> row) => '${row['period'] ?? row['month'] ?? ''}').toList(),
                              values: rows
                                  .map((Map<String, dynamic> row) => Fmt.toNum(row['total'] ?? row['amount'] ?? row['sales']) ?? 0)
                                  .toList(),
                              height: 240,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 16),
                      Expanded(
                        flex: 2,
                        child: SectionCard(
                          titleKey: 'dash.top_products',
                          child: AsyncView<List<Map<String, dynamic>>>(
                            value: ref.watch(topProductsProvider),
                            builder: (List<Map<String, dynamic>> rows) => SimpleBarChart(
                              labels: rows
                                  .take(8)
                                  .map((Map<String, dynamic> row) => '${row['name'] ?? row['sku'] ?? ''}')
                                  .toList(),
                              values: rows
                                  .take(8)
                                  .map((Map<String, dynamic> row) => Fmt.toNum(row['total'] ?? row['quantity'] ?? row['amount']) ?? 0)
                                  .toList(),
                              height: 240,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  _DocumentLists(data: data, locale: locale),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _KpiGrid extends StatelessWidget {
  const _KpiGrid({required this.data, required this.locale, required this.currency});

  final Map<String, dynamic> data;
  final String locale;
  final String currency;

  static const Map<String, String> _labels = <String, String>{
    'sales': 'dash.sales',
    'sales_total': 'dash.sales',
    'purchases': 'dash.purchases',
    'purchases_total': 'dash.purchases',
    'gross_profit': 'dash.gross_profit',
    'receivables': 'dash.receivables',
    'payables': 'dash.payables',
    'cash_position': 'dash.cash',
    'cash': 'dash.cash',
    'stock_value': 'dash.stock_value',
    'inventory_value': 'dash.stock_value',
    'headcount': 'dash.headcount',
    'active_projects': 'dash.projects',
    'open_tickets': 'dash.tickets',
    'pending_approvals': 'dash.pending_approvals',
    'open_shifts': 'dash.open_pos',
    'low_stock_count': 'dash.low_stock',
  };

  @override
  Widget build(BuildContext context) {
    final Map<String, dynamic> cards = _collect(data);

    final List<String> moneyKeys = <String>[
      'sales',
      'sales_total',
      'purchases',
      'purchases_total',
      'gross_profit',
      'receivables',
      'payables',
      'cash_position',
      'cash',
      'stock_value',
      'inventory_value',
    ];

    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final int perRow = constraints.maxWidth > 1400
            ? 4
            : constraints.maxWidth > 1000
                ? 3
                : 2;
        final double width = (constraints.maxWidth - (perRow - 1) * 12) / perRow;
        if (cards.isEmpty) {
          return const EmptyState(messageKey: 'dash.no_data');
        }
        return Wrap(
          spacing: 12,
          runSpacing: 12,
          children: <Widget>[
            for (final MapEntry<String, dynamic> entry in cards.entries)
              SizedBox(
                width: width,
                child: KpiCard(
                  labelKey: _labels[entry.key] ?? 'dash.kpis',
                  value: moneyKeys.contains(entry.key)
                      ? Fmt.money(entry.value, locale: locale, currency: currency)
                      : Fmt.number(entry.value, locale: locale),
                  icon: _iconFor(entry.key),
                  caption: entry.key,
                ),
              ),
          ],
        );
      },
    );
  }

  /// Dashboard payloads group their numbers under `kpis`, `cards` or `metrics`
  /// depending on the role template; flatten all of them for the grid.
  static Map<String, dynamic> _collect(Map<String, dynamic> data) {
    final Map<String, dynamic> out = <String, dynamic>{};
    for (final String key in <String>['kpis', 'cards', 'metrics', 'totals']) {
      final Object? value = data[key];
      if (value is Map) {
        value.forEach((Object? name, Object? metric) {
          if (metric is num || metric is String) out['$name'] = metric;
        });
      }
    }
    return out;
  }

  IconData _iconFor(String key) {
    if (key.contains('sale')) return Icons.trending_up;
    if (key.contains('purchase')) return Icons.shopping_bag_outlined;
    if (key.contains('cash')) return Icons.payments_outlined;
    if (key.contains('receiv')) return Icons.download_outlined;
    if (key.contains('pay')) return Icons.upload_outlined;
    if (key.contains('stock') || key.contains('inventory')) return Icons.inventory_2_outlined;
    if (key.contains('ticket')) return Icons.support_agent;
    if (key.contains('project')) return Icons.workspaces_outline;
    if (key.contains('head')) return Icons.groups_outlined;
    return Icons.insights_outlined;
  }
}

class _DocumentLists extends StatelessWidget {
  const _DocumentLists({required this.data, required this.locale});

  final Map<String, dynamic> data;
  final String locale;

  @override
  Widget build(BuildContext context) {
    final List<Widget> panels = <Widget>[];
    for (final String key in <String>['recent_documents', 'recent_invoices', 'overdue_invoices', 'pending_approvals', 'low_stock']) {
      final Object? rows = data[key];
      if (rows is List && rows.isNotEmpty) {
        panels.add(
          SizedBox(
            width: 460,
            child: SectionCard(
              titleKey: switch (key) {
                'recent_documents' => 'dash.recent_documents',
                'recent_invoices' => 'nav.sales',
                'overdue_invoices' => 'dash.overdue_invoices',
                'pending_approvals' => 'dash.pending_approvals',
                _ => 'dash.low_stock',
              },
              child: Column(
                children: <Widget>[
                  for (final Object? row in rows.take(6))
                    if (row is Map<String, dynamic>)
                      ListTile(
                        dense: true,
                        title: Text(
                          '${row['document_no'] ?? row['name'] ?? row['sku'] ?? row['id']}',
                          overflow: TextOverflow.ellipsis,
                        ),
                        subtitle: Text(
                          '${Fmt.date(row['document_date'] ?? row['created_at'] ?? row['due_date'], locale: locale)}'
                          ' ${row['party_name'] ?? row['customer_name'] ?? ''}',
                        ),
                        trailing: row['status'] != null
                            ? StatusChip(row['status'], compact: true)
                            : CountChip(
                                Fmt.money(row['total_amount'] ?? row['quantity'] ?? row['balance'], locale: locale),
                              ),
                      ),
                ],
              ),
            ),
          ),
        );
      }
    }
    if (panels.isEmpty) return const SizedBox.shrink();
    return Wrap(spacing: 16, runSpacing: 16, children: panels);
  }
}
