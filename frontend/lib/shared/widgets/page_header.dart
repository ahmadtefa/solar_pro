import 'package:flutter/material.dart';

import '../../core/l10n/app_strings.dart';

/// Title block used on top of every page: breadcrumbs, title, subtitle and actions.
class PageHeader extends StatelessWidget {
  const PageHeader({
    required this.titleKey,
    this.subtitle,
    this.actions = const <Widget>[],
    this.breadcrumbs = const <String>[],
    super.key,
  });

  final String titleKey;
  final String? subtitle;
  final List<Widget> actions;
  final List<String> breadcrumbs;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          if (breadcrumbs.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Wrap(
                spacing: 6,
                children: <Widget>[
                  for (int index = 0; index < breadcrumbs.length; index++) ...<Widget>[
                    if (index > 0)
                      Icon(Icons.chevron_right, size: 14, color: theme.colorScheme.outline),
                    Text(
                      context.tr(breadcrumbs[index]),
                      style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                    ),
                  ],
                ],
              ),
            ),
          Row(
            children: <Widget>[
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(context.tr(titleKey), style: theme.textTheme.headlineSmall),
                    if (subtitle != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(
                          subtitle!,
                          style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                        ),
                      ),
                  ],
                ),
              ),
              Wrap(spacing: 8, children: actions),
            ],
          ),
        ],
      ),
    );
  }
}

/// Card used to group content inside a page.
class SectionCard extends StatelessWidget {
  const SectionCard({required this.child, this.titleKey, this.actions = const <Widget>[], this.padding, super.key});

  final Widget child;
  final String? titleKey;
  final List<Widget> actions;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: padding ?? const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            if (titleKey != null) ...<Widget>[
              Row(
                children: <Widget>[
                  Expanded(
                    child: Text(
                      context.tr(titleKey!),
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                  ),
                  ...actions,
                ],
              ),
              const SizedBox(height: 12),
            ],
            child,
          ],
        ),
      ),
    );
  }
}

/// Compact KPI tile used by dashboards.
class KpiCard extends StatelessWidget {
  const KpiCard({
    required this.labelKey,
    required this.value,
    this.icon,
    this.trendPercent,
    this.caption,
    this.color,
    super.key,
  });

  final String labelKey;
  final String value;
  final IconData? icon;
  final num? trendPercent;
  final String? caption;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final Color accent = color ?? theme.colorScheme.primary;
    final bool? up = trendPercent == null ? null : trendPercent! >= 0;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                if (icon != null) ...<Widget>[
                  Container(
                    padding: const EdgeInsets.all(6),
                    decoration: BoxDecoration(
                      color: accent.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Icon(icon, size: 16, color: accent),
                  ),
                  const SizedBox(width: 8),
                ],
                Expanded(
                  child: Text(
                    context.tr(labelKey),
                    style: theme.textTheme.labelMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(value, style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w600)),
            if (trendPercent != null) ...<Widget>[
              const SizedBox(height: 6),
              Row(
                children: <Widget>[
                  Icon(
                    up! ? Icons.trending_up : Icons.trending_down,
                    size: 14,
                    color: up ? Colors.green.shade600 : theme.colorScheme.error,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    '${trendPercent!.toStringAsFixed(1)}%',
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: up ? Colors.green.shade700 : theme.colorScheme.error,
                    ),
                  ),
                ],
              ),
            ],
            if (caption != null) ...<Widget>[
              const SizedBox(height: 4),
              Text(caption!, style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.outline)),
            ],
          ],
        ),
      ),
    );
  }
}
