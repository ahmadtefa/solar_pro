import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/l10n/app_strings.dart';
import '../../../core/providers.dart';
import '../../../core/utils/formatters.dart';
import '../../../shared/widgets/async_view.dart';

/// Live unread counter with a dropdown list of the latest notifications.
final unreadCountProvider = FutureProvider<int>((Ref ref) async {
  final Map<String, dynamic> payload = await ref.watch(apiProvider).object('/notifications/unread-count');
  final Object? value = payload['count'] ?? payload['unread'] ?? payload['total'];
  return int.tryParse('$value') ?? 0;
});

class NotificationBell extends ConsumerWidget {
  const NotificationBell({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final int unread = ref.watch(unreadCountProvider).valueOrNull ?? 0;
    return IconButton(
      tooltip: context.tr('common.notifications'),
      onPressed: () => context.go('/notifications'),
      icon: Badge(
        isLabelVisible: unread > 0,
        label: Text('$unread'),
        child: const Icon(Icons.notifications_none),
      ),
    );
  }
}

class NotificationsPage extends ConsumerStatefulWidget {
  const NotificationsPage({super.key});

  @override
  ConsumerState<NotificationsPage> createState() => _NotificationsPageState();
}

class _NotificationsPageState extends ConsumerState<NotificationsPage> {
  List<Map<String, dynamic>> _items = <Map<String, dynamic>>[];
  bool _loading = true;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<Map<String, dynamic>> items =
          await ref.read(apiProvider).collection('/notifications', query: <String, dynamic>{'page_size': 50});
      if (mounted) {
        setState(() {
          _items = items;
          _loading = false;
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          _error = error;
          _loading = false;
        });
      }
    }
  }

  Future<void> _markAllRead() async {
    try {
      await ref.read(apiProvider).create('/notifications/read-all', <String, dynamic>{});
      ref.invalidate(unreadCountProvider);
      await _load();
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$error')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final String locale = Localizations.localeOf(context).languageCode;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
          child: Row(
            children: <Widget>[
              Expanded(
                child: Text(context.tr('common.notifications'), style: Theme.of(context).textTheme.headlineSmall),
              ),
              OutlinedButton.icon(
                onPressed: _markAllRead,
                icon: const Icon(Icons.done_all, size: 18),
                label: Text(context.tr('common.mark_all_read')),
              ),
              const SizedBox(width: 8),
              IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
            ],
          ),
        ),
        Expanded(
          child: _loading
              ? const LoadingState()
              : _error != null
                  ? ErrorState(error: _error!, onRetry: _load)
                  : _items.isEmpty
                      ? const EmptyState()
                      : ListView.builder(
                          padding: const EdgeInsets.symmetric(horizontal: 20),
                          itemCount: _items.length,
                          itemBuilder: (BuildContext context, int index) {
                            final Map<String, dynamic> item = _items[index];
                            final bool read = Fmt.toBool(item['is_read']);
                            return Card(
                              margin: const EdgeInsets.only(bottom: 8),
                              child: ListTile(
                                leading: Icon(
                                  read ? Icons.mark_email_read_outlined : Icons.mark_email_unread_outlined,
                                  color: read ? Theme.of(context).colorScheme.outline : Theme.of(context).colorScheme.primary,
                                ),
                                title: Text('${item['title'] ?? item['subject'] ?? ''}'),
                                subtitle: Text(
                                  '${item['body'] ?? item['message'] ?? ''}\n'
                                  '${Fmt.relative(item['created_at'], locale: locale)}',
                                ),
                                isThreeLine: true,
                                trailing: Text('${item['notification_type'] ?? item['channel'] ?? ''}'),
                              ),
                            );
                          },
                        ),
        ),
      ],
    );
  }
}
