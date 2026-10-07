import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/l10n/app_strings.dart';
import '../../core/network/api_exception.dart';

/// Renders an [AsyncValue] with consistent loading, empty and error states.
class AsyncView<T> extends StatelessWidget {
  const AsyncView({
    required this.value,
    required this.builder,
    this.isEmpty,
    this.onRetry,
    this.loading,
    super.key,
  });

  final AsyncValue<T> value;
  final Widget Function(T data) builder;
  final bool Function(T data)? isEmpty;
  final VoidCallback? onRetry;
  final Widget? loading;

  @override
  Widget build(BuildContext context) {
    return value.when(
      data: (T data) {
        final bool empty = isEmpty?.call(data) ?? false;
        return empty ? EmptyState(onRetry: onRetry) : builder(data);
      },
      loading: () => loading ?? const LoadingState(),
      error: (Object error, StackTrace stack) => ErrorState(error: error, onRetry: onRetry),
    );
  }
}

class LoadingState extends StatelessWidget {
  const LoadingState({super.key});

  @override
  Widget build(BuildContext context) => const Padding(
        padding: EdgeInsets.symmetric(vertical: 48),
        child: Center(child: CircularProgressIndicator()),
      );
}

class EmptyState extends StatelessWidget {
  const EmptyState({this.messageKey = 'common.no_data', this.hintKey, this.onRetry, this.icon, super.key});

  final String messageKey;
  final String? hintKey;
  final VoidCallback? onRetry;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 40, horizontal: 24),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(icon ?? Icons.inbox_outlined, size: 44, color: theme.colorScheme.outline),
            const SizedBox(height: 12),
            Text(context.tr(messageKey), style: theme.textTheme.titleMedium),
            if (hintKey != null) ...<Widget>[
              const SizedBox(height: 6),
              Text(
                context.tr(hintKey!),
                style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                textAlign: TextAlign.center,
              ),
            ],
            if (onRetry != null) ...<Widget>[
              const SizedBox(height: 16),
              OutlinedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
                label: Text(context.tr('common.retry')),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class ErrorState extends StatelessWidget {
  const ErrorState({required this.error, this.onRetry, super.key});

  final Object error;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String message = error is ApiException
        ? (error as ApiException).localized(context)
        : context.tr('error.unknown');
    final Map<String, String> fields = error is ApiException ? (error as ApiException).fieldErrors : const <String, String>{};
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 32, horizontal: 24),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(Icons.error_outline, size: 44, color: theme.colorScheme.error),
            const SizedBox(height: 12),
            Text(context.tr('common.error_title'), style: theme.textTheme.titleMedium),
            const SizedBox(height: 6),
            Text(message, textAlign: TextAlign.center, style: theme.textTheme.bodySmall),
            if (fields.isNotEmpty) ...<Widget>[
              const SizedBox(height: 12),
              for (final MapEntry<String, String> entry in fields.entries)
                Text('${entry.key}: ${entry.value}', style: theme.textTheme.bodySmall),
            ],
            if (onRetry != null) ...<Widget>[
              const SizedBox(height: 16),
              OutlinedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
                label: Text(context.tr('common.retry')),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
