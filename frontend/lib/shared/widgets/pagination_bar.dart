import 'package:flutter/material.dart';

import '../../core/config/app_config.dart';
import '../../core/l10n/app_strings.dart';

/// Page navigation plus the page-size selector, shared by every data table.
class PaginationBar extends StatelessWidget {
  const PaginationBar({
    required this.page,
    required this.pages,
    required this.total,
    required this.pageSize,
    required this.onPageChanged,
    required this.onPageSizeChanged,
    super.key,
  });

  final int page;
  final int pages;
  final int total;
  final int pageSize;
  final ValueChanged<int> onPageChanged;
  final ValueChanged<int> onPageSizeChanged;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final int safePages = pages < 1 ? 1 : pages;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
      child: Row(
        children: <Widget>[
          Text(
            '${context.tr('common.total')}: $total ${context.tr('common.rows')}',
            style: theme.textTheme.labelMedium,
          ),
          const Spacer(),
          DropdownButton<int>(
            value: AppConfig.pageSizes.contains(pageSize) ? pageSize : AppConfig.pageSizes.last,
            underline: const SizedBox.shrink(),
            items: <DropdownMenuItem<int>>[
              for (final int size in AppConfig.pageSizes)
                DropdownMenuItem<int>(value: size, child: Text('$size / ${context.tr('common.page')}')),
            ],
            onChanged: (int? value) {
              if (value != null) onPageSizeChanged(value);
            },
          ),
          const SizedBox(width: 12),
          IconButton(
            tooltip: context.tr('common.previous'),
            onPressed: page > 1 ? () => onPageChanged(page - 1) : null,
            icon: const Icon(Icons.chevron_left),
          ),
          Text('${context.tr('common.page')} $page ${context.tr('common.of')} $safePages'),
          IconButton(
            tooltip: context.tr('common.next'),
            onPressed: page < safePages ? () => onPageChanged(page + 1) : null,
            icon: const Icon(Icons.chevron_right),
          ),
        ],
      ),
    );
  }
}
