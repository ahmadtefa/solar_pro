import '../data/models/quote_item.dart';

/// The money columns of a quote, computed from its line items.
///
/// Pure logic (no database, no Flutter) so it can be unit tested directly and
/// reused by the form, the detail screen, the PDF generator and the reports.
///
/// Conventions used by the whole app:
/// * every item has a [quantity] and a [unitPrice];
/// * `discount` and `tax` on [Quote] are **percentages**, not amounts;
/// * the discount is applied first, the tax is applied to the discounted
///   subtotal, and the result is what gets stored in `Quote.totalPrice`.
class QuoteTotals {
  /// Sum of `quantity × unitPrice` over all items, before discount and tax.
  final double subtotal;

  /// Discount percentage (0 - 100).
  final double discountPercent;

  /// Tax percentage (0 - 100), applied after the discount.
  final double taxPercent;

  /// `subtotal × discountPercent / 100`.
  final double discountAmount;

  /// `(subtotal - discountAmount) × taxPercent / 100`.
  final double taxAmount;

  /// What the customer actually pays.
  final double total;

  const QuoteTotals({
    required this.subtotal,
    required this.discountPercent,
    required this.taxPercent,
    required this.discountAmount,
    required this.taxAmount,
    required this.total,
  });

  /// Computes the totals of a quote from its [items].
  ///
  /// [discountPercent] is clamped to `0..100` and [taxPercent] to `0..100` so a
  /// typo in a text field can never produce a negative total.
  factory QuoteTotals.compute({
    required List<QuoteItem> items,
    double discountPercent = 0,
    double taxPercent = 0,
  }) {
    final subtotal = items.fold<double>(
      0,
      (sum, item) => sum + item.lineTotal,
    );

    final discount = _clampPercent(discountPercent);
    final tax = _clampPercent(taxPercent);

    final discountAmount = subtotal * discount / 100;
    final afterDiscount = subtotal - discountAmount;
    final taxAmount = afterDiscount * tax / 100;

    return QuoteTotals(
      subtotal: subtotal,
      discountPercent: discount,
      taxPercent: tax,
      discountAmount: discountAmount,
      taxAmount: taxAmount,
      total: afterDiscount + taxAmount,
    );
  }

  static double _clampPercent(double value) {
    if (value.isNaN) return 0;
    if (value < 0) return 0;
    if (value > 100) return 100;
    return value;
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is QuoteTotals &&
          runtimeType == other.runtimeType &&
          subtotal == other.subtotal &&
          discountPercent == other.discountPercent &&
          taxPercent == other.taxPercent &&
          discountAmount == other.discountAmount &&
          taxAmount == other.taxAmount &&
          total == other.total;

  @override
  int get hashCode => Object.hash(
        subtotal,
        discountPercent,
        taxPercent,
        discountAmount,
        taxAmount,
        total,
      );

  @override
  String toString() {
    return 'QuoteTotals(subtotal: $subtotal, discount: $discountPercent%, tax: $taxPercent%, total: $total)';
  }
}
