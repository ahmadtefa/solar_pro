import 'package:flutter/material.dart';

import '../../core/l10n/app_strings.dart';
import '../../core/utils/formatters.dart';

/// Colour-coded chip for document and record statuses.
class StatusChip extends StatelessWidget {
  const StatusChip(this.status, {this.compact = false, super.key});

  final Object? status;
  final bool compact;

  Color _color(ColorScheme scheme) {
    switch ('$status'.toLowerCase()) {
      case 'posted':
      case 'approved':
      case 'completed':
      case 'paid':
      case 'fulfilled':
      case 'active':
        return scheme.primary;
      case 'rejected':
      case 'cancelled':
      case 'overdue':
        return scheme.error;
      case 'submitted':
      case 'in_progress':
      case 'partially_paid':
      case 'partially_fulfilled':
      case 'pending':
        return scheme.tertiary;
      case 'draft':
      case 'open':
      default:
        return scheme.outline;
    }
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final Color color = _color(scheme);
    final String label = context.tr(Fmt.statusKey(status));
    return Container(
      padding: EdgeInsets.symmetric(horizontal: compact ? 6 : 8, vertical: compact ? 1 : 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Text(
        label,
        style: TextStyle(fontSize: compact ? 10.5 : 11.5, color: color, fontWeight: FontWeight.w600),
      ),
    );
  }
}

/// Small pill used for counts and money in tables.
class CountChip extends StatelessWidget {
  const CountChip(this.label, {this.icon, this.color, super.key});

  final String label;
  final IconData? icon;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final Color effective = color ?? scheme.primary;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: effective.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (icon != null) ...<Widget>[Icon(icon, size: 14, color: effective), const SizedBox(width: 6)],
          Text(label, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: effective)),
        ],
      ),
    );
  }
}
