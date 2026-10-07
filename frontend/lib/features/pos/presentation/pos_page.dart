import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/l10n/app_strings.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/providers.dart';
import '../../../core/utils/formatters.dart';
import '../../../shared/widgets/async_view.dart';
import '../../../shared/widgets/dialogs.dart';
import '../../../shared/widgets/notify.dart';
import '../../../shared/widgets/status_chip.dart';

/// Touch friendly point-of-sale terminal wired to the real POS endpoints:
/// terminals, shifts, cash movements, sales and returns.
class PosPage extends ConsumerStatefulWidget {
  const PosPage({super.key});

  @override
  ConsumerState<PosPage> createState() => _PosPageState();
}

class _PosLine {
  _PosLine({required this.product, required this.quantity});

  final Map<String, dynamic> product;
  double quantity;

  String get key => '${product['id']}';
  num get price => Fmt.toNum(product['sales_price'] ?? product['price']) ?? 0;
  num get total => price * quantity;
}

class _PosPageState extends ConsumerState<PosPage> {
  final TextEditingController _scanController = TextEditingController();
  final TextEditingController _searchController = TextEditingController();
  final List<_PosLine> _lines = <_PosLine>[];
  List<Map<String, dynamic>> _terminals = <Map<String, dynamic>>[];
  Map<String, dynamic>? _terminal;
  Map<String, dynamic>? _shift;
  List<Map<String, dynamic>> _results = <Map<String, dynamic>>[];
  String _paymentMethod = 'cash';
  double _paid = 0;
  double _discountPercent = 0;
  bool _busy = false;
  String? _status;

  @override
  void initState() {
    super.initState();
    _loadTerminals();
  }

  @override
  void dispose() {
    _scanController.dispose();
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _loadTerminals() async {
    setState(() => _busy = true);
    try {
      final List<Map<String, dynamic>> terminals =
          await ref.read(apiProvider).collection('/pos/terminals', query: <String, dynamic>{'page_size': 50});
      if (!mounted) return;
      setState(() {
        _terminals = terminals;
        _terminal = terminals.isNotEmpty ? terminals.first : null;
      });
      await _loadShift();
    } catch (error) {
      if (mounted) setState(() => _status = _message(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _loadShift() async {
    final Map<String, dynamic>? terminal = _terminal;
    if (terminal == null) return;
    try {
      final Map<String, dynamic> payload = await ref.read(apiProvider).object(
            '/pos/shifts/open',
            query: <String, dynamic>{'terminal_id': terminal['id']},
          );
      final Object? shift = payload['shift'] ?? payload['item'];
      if (mounted) {
        setState(() => _shift = shift is Map<String, dynamic> ? shift : (payload['id'] != null ? payload : null));
      }
    } on ApiException {
      if (mounted) setState(() => _shift = null);
    }
  }

  String _message(Object error) =>
      error is ApiException ? error.localized(context) : context.tr('error.unknown');

  num get _subtotal => _lines.fold<num>(0, (num sum, _PosLine line) => sum + line.total);
  num get _discount => _subtotal * _discountPercent / 100;
  num get _total => _subtotal - _discount;
  num get _change => _paid > _total ? _paid - _total : 0;

  Future<void> _search(String term) async {
    if (term.trim().length < 2) {
      setState(() => _results = <Map<String, dynamic>>[]);
      return;
    }
    try {
      final Map<String, dynamic> payload = await ref.read(apiProvider).object(
            '/pos/lookup',
            query: <String, dynamic>{'q': term.trim(), 'terminal_id': _terminal?['id']},
          );
      final Object? items = payload['items'] ?? payload['products'];
      if (mounted && items is List) {
        setState(() => _results = items.whereType<Map<String, dynamic>>().toList());
      }
    } catch (error) {
      if (mounted) setState(() => _status = _message(error));
    }
  }

  void _addProduct(Map<String, dynamic> product) {
    final String id = '${product['id']}';
    final int index = _lines.indexWhere((_PosLine line) => line.key == id);
    setState(() {
      if (index >= 0) {
        _lines[index].quantity += 1;
      } else {
        _lines.add(_PosLine(product: product, quantity: 1));
      }
      _results = <Map<String, dynamic>>[];
      _searchController.clear();
      _scanController.clear();
      _status = null;
    });
  }

  Future<void> _openShift() async {
    final Map<String, dynamic>? terminal = _terminal;
    if (terminal == null) return;
    final TextEditingController opening = TextEditingController(text: '0');
    final double? amount = await showDialog<double>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: Text(dialogContext.tr('pos.open_shift')),
        content: TextField(
          controller: opening,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(labelText: dialogContext.tr('pos.opening_cash')),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: Text(dialogContext.tr('common.cancel')),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(double.tryParse(opening.text) ?? 0),
            child: Text(dialogContext.tr('pos.open_shift')),
          ),
        ],
      ),
    );
    if (amount == null) return;
    try {
      await ref.read(apiProvider).create('/pos/shifts/open', <String, dynamic>{
        'terminal_id': terminal['id'],
        'opening_cash': amount,
      });
      await _loadShift();
      if (mounted) context.showSuccess('common.saved');
    } catch (error) {
      if (mounted) setState(() => _status = _message(error));
    }
  }

  Future<void> _closeShift() async {
    final Map<String, dynamic>? shift = _shift;
    if (shift == null) return;
    final TextEditingController counted = TextEditingController();
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: Text(dialogContext.tr('pos.close_shift')),
        content: TextField(
          controller: counted,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(labelText: dialogContext.tr('pos.counted_cash')),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: Text(dialogContext.tr('common.cancel')),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: Text(dialogContext.tr('pos.close_shift')),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ref.read(apiProvider).create('/pos/shifts/${shift['id']}/close', <String, dynamic>{
        'counted_cash': double.tryParse(counted.text) ?? 0,
      });
      await _loadShift();
      if (mounted) context.showSuccess('common.saved');
    } catch (error) {
      if (mounted) setState(() => _status = _message(error));
    }
  }

  Future<void> _checkout() async {
    final Map<String, dynamic>? terminal = _terminal;
    if (terminal == null) return;
    if (_shift == null) {
      if (mounted) setState(() => _status = context.tr('pos.no_shift'));
      return;
    }
    if (_lines.isEmpty) return;
    setState(() => _busy = true);
    try {
      final Map<String, dynamic> payload = <String, dynamic>{
        'terminal_id': terminal['id'],
        'shift_id': _shift!['id'],
        'payment_method': _paymentMethod,
        'paid_amount': _paid == 0 ? _total : _paid,
        'discount_percent': _discountPercent,
        'lines': <Map<String, dynamic>>[
          for (final _PosLine line in _lines)
            <String, dynamic>{
              'product_id': line.product['id'],
              'quantity': line.quantity,
              'unit_price': line.price,
            },
        ],
      };
      final Map<String, dynamic> sale = await ref.read(apiProvider).create('/pos/sales', payload);
      if (!mounted) return;
      final String documentNo = '${sale['document_no'] ?? sale['invoice_no'] ?? ''}';
      setState(() {
        _lines.clear();
        _paid = 0;
        _discountPercent = 0;
        _status = null;
      });
      await ref.read(apiProvider).documentAction('/pos/sales', '${sale['id']}', 'post');
      await _loadShift();
      if (!mounted) return;
      context.showSuccess('pos.sale_completed');
      await infoDialog(
        context,
        title: context.tr('pos.receipt'),
        content: Text('$documentNo\n${context.tr('common.grand_total')}: '
            '${Fmt.money(sale['total_amount'] ?? _total, currency: '${sale['currency_code'] ?? ''}')}'),
      );
    } catch (error) {
      if (mounted) setState(() => _status = _message(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _cashMovement(String direction) async {
    final Map<String, dynamic>? shift = _shift;
    if (shift == null) return;
    final TextEditingController amount = TextEditingController();
    final TextEditingController reason = TextEditingController();
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: Text('${dialogContext.tr('pos.cash_movement')} - ${dialogContext.tr(direction == 'in' ? 'pos.cash_in' : 'pos.cash_out')}'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            TextField(
              controller: amount,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: InputDecoration(labelText: dialogContext.tr('common.amount')),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: reason,
              decoration: InputDecoration(labelText: dialogContext.tr('common.reason')),
            ),
          ],
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: Text(dialogContext.tr('common.cancel')),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: Text(dialogContext.tr('common.save')),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ref.read(apiProvider).create('/pos/cash-movements', <String, dynamic>{
        'shift_id': shift['id'],
        'direction': direction,
        'amount': double.tryParse(amount.text) ?? 0,
        'reason': reason.text,
      });
      await _loadShift();
      if (mounted) context.showSuccess('common.saved');
    } catch (error) {
      if (mounted) setState(() => _status = _message(error));
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Row(
                  children: <Widget>[
                    Icon(Icons.point_of_sale, color: theme.colorScheme.primary),
                    const SizedBox(width: 8),
                    Text(context.tr('pos.title'), style: theme.textTheme.titleLarge),
                  ],
                ),
              ),
              if (_terminals.length > 1)
                SizedBox(
                  width: 220,
                  child: DropdownButtonFormField<Map<String, dynamic>>(
                    value: _terminal,
                    isExpanded: true,
                    decoration: InputDecoration(labelText: context.tr('pos.terminal')),
                    items: <DropdownMenuItem<Map<String, dynamic>>>[
                      for (final Map<String, dynamic> terminal in _terminals)
                        DropdownMenuItem<Map<String, dynamic>>(
                          value: terminal,
                          child: Text('${terminal['name']}'),
                        ),
                    ],
                    onChanged: (Map<String, dynamic>? value) async {
                      setState(() => _terminal = value);
                      await _loadShift();
                    },
                  ),
                ),
              const SizedBox(width: 8),
              if (_shift == null)
                FilledButton.icon(
                  onPressed: _busy ? null : _openShift,
                  icon: const Icon(Icons.lock_open, size: 18),
                  label: Text(context.tr('pos.open_shift')),
                )
              else ...<Widget>[
                CountChip(
                  '${context.tr('pos.shift')}: ${_shift!['shift_no'] ?? ''}',
                  icon: Icons.schedule_outlined,
                ),
                const SizedBox(width: 8),
                OutlinedButton.icon(
                  onPressed: () => _cashMovement('in'),
                  icon: const Icon(Icons.add, size: 16),
                  label: Text(context.tr('pos.cash_in')),
                ),
                const SizedBox(width: 8),
                OutlinedButton.icon(
                  onPressed: () => _cashMovement('out'),
                  icon: const Icon(Icons.remove, size: 16),
                  label: Text(context.tr('pos.cash_out')),
                ),
                const SizedBox(width: 8),
                OutlinedButton.icon(
                  onPressed: _closeShift,
                  icon: const Icon(Icons.lock_outline, size: 16),
                  label: Text(context.tr('pos.close_shift')),
                ),
              ],
            ],
          ),
          if (_status != null)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Row(
                children: <Widget>[
                  Icon(Icons.info_outline, size: 16, color: theme.colorScheme.error),
                  const SizedBox(width: 6),
                  Expanded(child: Text(_status!, style: TextStyle(color: theme.colorScheme.error, fontSize: 12.5))),
                ],
              ),
            ),
          const SizedBox(height: 8),
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Expanded(
                  flex: 2,
                  child: Column(
                    children: <Widget>[
                      TextField(
                        controller: _searchController,
                        onSubmitted: _search,
                        onChanged: _search,
                        decoration: InputDecoration(
                          hintText: context.tr('pos.scan'),
                          prefixIcon: const Icon(Icons.qr_code_scanner),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Expanded(
                        child: _results.isEmpty
                            ? EmptyState(messageKey: 'pos.scan', hintKey: 'common.search_hint', icon: Icons.qr_code_2)
                            : ListView.builder(
                                itemCount: _results.length,
                                itemBuilder: (BuildContext context, int index) {
                                  final Map<String, dynamic> product = _results[index];
                                  return Card(
                                    margin: const EdgeInsets.only(bottom: 6),
                                    child: ListTile(
                                      title: Text('${product['name']}'),
                                      subtitle: Text(
                                        '${product['sku'] ?? ''} · ${Fmt.money(product['sales_price'] ?? product['price'])}',
                                      ),
                                      trailing: FilledButton.tonal(
                                        onPressed: () => _addProduct(product),
                                        child: Text(context.tr('common.select')),
                                      ),
                                    ),
                                  );
                                },
                              ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  flex: 3,
                  child: Card(
                    child: Column(
                      children: <Widget>[
                        Padding(
                          padding: const EdgeInsets.all(12),
                          child: Row(
                            children: <Widget>[
                              Expanded(
                                child: Text(context.tr('pos.cart'), style: theme.textTheme.titleMedium),
                              ),
                              TextButton.icon(
                                onPressed: _lines.isEmpty ? null : () => setState(_lines.clear),
                                icon: const Icon(Icons.clear_all, size: 16),
                                label: Text(context.tr('pos.clear')),
                              ),
                            ],
                          ),
                        ),
                        const Divider(height: 1),
                        Expanded(
                          child: _lines.isEmpty
                              ? const EmptyState(messageKey: 'pos.cart', icon: Icons.shopping_basket_outlined)
                              : ListView.builder(
                                  itemCount: _lines.length,
                                  itemBuilder: (BuildContext context, int index) {
                                    final _PosLine line = _lines[index];
                                    return ListTile(
                                      dense: true,
                                      title: Text('${line.product['name']}'),
                                      subtitle: Text('${Fmt.money(line.price)} × ${line.quantity}'),
                                      trailing: Row(
                                        mainAxisSize: MainAxisSize.min,
                                        children: <Widget>[
                                          IconButton(
                                            icon: const Icon(Icons.remove_circle_outline, size: 18),
                                            onPressed: () => setState(() {
                                              line.quantity -= 1;
                                              if (line.quantity <= 0) _lines.removeAt(index);
                                            }),
                                          ),
                                          Text('${line.quantity}'),
                                          IconButton(
                                            icon: const Icon(Icons.add_circle_outline, size: 18),
                                            onPressed: () => setState(() => line.quantity += 1),
                                          ),
                                          SizedBox(
                                            width: 90,
                                            child: Text(
                                              Fmt.money(line.total),
                                              textAlign: TextAlign.end,
                                            ),
                                          ),
                                        ],
                                      ),
                                    );
                                  },
                                ),
                        ),
                        const Divider(height: 1),
                        Padding(
                          padding: const EdgeInsets.all(12),
                          child: Column(
                            children: <Widget>[
                              _totalRow(context, 'common.subtotal', _subtotal),
                              _totalRow(context, 'common.discount', _discount),
                              Row(
                                children: <Widget>[
                                  Expanded(child: Text(context.tr('pos.discount'))),
                                  SizedBox(
                                    width: 120,
                                    child: TextField(
                                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                                      decoration: const InputDecoration(suffixText: '%'),
                                      onChanged: (String value) =>
                                          setState(() => _discountPercent = double.tryParse(value) ?? 0),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 6),
                              _totalRow(context, 'common.grand_total', _total, emphasize: true),
                              const SizedBox(height: 8),
                              Row(
                                children: <Widget>[
                                  Expanded(
                                    child: DropdownButtonFormField<String>(
                                      value: _paymentMethod,
                                      decoration: InputDecoration(labelText: context.tr('pos.payment_method')),
                                      items: <DropdownMenuItem<String>>[
                                        DropdownMenuItem<String>(value: 'cash', child: Text(context.tr('pos.cash'))),
                                        DropdownMenuItem<String>(value: 'card', child: Text(context.tr('pos.card'))),
                                        DropdownMenuItem<String>(value: 'wallet', child: Text(context.tr('pos.wallet'))),
                                        DropdownMenuItem<String>(value: 'credit', child: Text(context.tr('pos.credit'))),
                                      ],
                                      onChanged: (String? value) => setState(() => _paymentMethod = value ?? 'cash'),
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  SizedBox(
                                    width: 140,
                                    child: TextField(
                                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                                      decoration: InputDecoration(labelText: context.tr('pos.paid')),
                                      onChanged: (String value) => setState(() => _paid = double.tryParse(value) ?? 0),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 6),
                              _totalRow(context, 'pos.change', _change),
                              const SizedBox(height: 10),
                              SizedBox(
                                width: double.infinity,
                                child: FilledButton.icon(
                                  onPressed: _busy || _lines.isEmpty ? null : _checkout,
                                  icon: const Icon(Icons.point_of_sale, size: 18),
                                  label: Text(context.tr('pos.pay')),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _totalRow(BuildContext context, String labelKey, num value, {bool emphasize = false}) {
    final TextStyle? style = emphasize
        ? Theme.of(context).textTheme.titleMedium
        : Theme.of(context).textTheme.bodyMedium;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: <Widget>[
          Expanded(child: Text(context.tr(labelKey), style: style)),
          Text(Fmt.money(value), style: style),
        ],
      ),
    );
  }
}
