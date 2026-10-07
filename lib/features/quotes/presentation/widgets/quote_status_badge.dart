import 'package:flutter/material.dart';

import '../../data/models/quote.dart';

/// Arabic labels, colours and icons for the five quote statuses.
extension QuoteStatusUi on QuoteStatus {
  String get labelAr {
    switch (this) {
      case QuoteStatus.draft:
        return 'مسودة';
      case QuoteStatus.sent:
        return 'مرسل';
      case QuoteStatus.accepted:
        return 'مقبول';
      case QuoteStatus.rejected:
        return 'مرفوض';
      case QuoteStatus.expired:
        return 'منتهي';
    }
  }

  Color get color {
    switch (this) {
      case QuoteStatus.draft:
        return const Color(0xFF6B7280); // grey
      case QuoteStatus.sent:
        return const Color(0xFF2563EB); // blue
      case QuoteStatus.accepted:
        return const Color(0xFF059669); // green
      case QuoteStatus.rejected:
        return const Color(0xFFDC2626); // red
      case QuoteStatus.expired:
        return const Color(0xFFD97706); // amber
    }
  }

  IconData get icon {
    switch (this) {
      case QuoteStatus.draft:
        return Icons.edit_note;
      case QuoteStatus.sent:
        return Icons.send;
      case QuoteStatus.accepted:
        return Icons.check_circle_outline;
      case QuoteStatus.rejected:
        return Icons.cancel_outlined;
      case QuoteStatus.expired:
        return Icons.hourglass_bottom;
    }
  }
}

/// Small coloured chip showing the status of a quote.
class QuoteStatusBadge extends StatelessWidget {
  const QuoteStatusBadge({super.key, required this.status});

  /// Raw status value as stored in the database.
  final String status;

  @override
  Widget build(BuildContext context) {
    final value = QuoteStatus.fromString(status);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: value.color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: value.color.withValues(alpha: 0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(value.icon, size: 14, color: value.color),
          const SizedBox(width: 4),
          Text(
            value.labelAr,
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: value.color,
            ),
          ),
        ],
      ),
    );
  }
}
