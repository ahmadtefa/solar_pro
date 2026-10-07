import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/l10n/app_strings.dart';
import '../../../core/models/auth_models.dart';
import '../../../core/providers.dart';
import '../../../core/utils/formatters.dart';
import '../../../shared/widgets/async_view.dart';
import '../../../shared/widgets/dialogs.dart';
import '../../../shared/widgets/notify.dart';
import '../../../shared/widgets/page_header.dart';
import '../../../shared/widgets/status_chip.dart';

final sessionsProvider = FutureProvider.autoDispose<List<Map<String, dynamic>>>(
  (Ref ref) => ref.watch(apiProvider).collection('/auth/sessions'),
);

final companyModulesProvider = FutureProvider.autoDispose<List<Map<String, dynamic>>>((Ref ref) async {
  final AuthState auth = ref.watch(authProvider);
  if (auth.company == null) return <Map<String, dynamic>>[];
  final Map<String, dynamic> payload = await ref.watch(apiProvider).object('/admin/companies/${auth.company!.id}/modules');
  final Object? items = payload['items'] ?? payload['modules'];
  return items is List ? items.whereType<Map<String, dynamic>>().toList() : <Map<String, dynamic>>[];
});

/// Personal + company settings: preferences, password, sessions and modules.
class SettingsPage extends ConsumerStatefulWidget {
  const SettingsPage({super.key});

  @override
  ConsumerState<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends ConsumerState<SettingsPage> with SingleTickerProviderStateMixin {
  late final TabController _tabs = TabController(length: 4, vsync: this);

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final AuthState auth = ref.watch(authProvider);
    return Column(
      children: <Widget>[
        PageHeader(titleKey: 'settings.title', breadcrumbs: <String>['group.platform', 'settings.preferences']),
        TabBar(
          controller: _tabs,
          isScrollable: true,
          tabs: <Widget>[
            Tab(text: context.tr('settings.preferences')),
            Tab(text: context.tr('password.change')),
            Tab(text: context.tr('session.title')),
            Tab(text: context.tr('settings.modules')),
          ],
        ),
        Expanded(
          child: TabBarView(
            controller: _tabs,
            children: <Widget>[
              _PreferencesTab(auth: auth),
              const _PasswordTab(),
              const _SessionsTab(),
              const _ModulesTab(),
            ],
          ),
        ),
      ],
    );
  }
}

class _PreferencesTab extends ConsumerWidget {
  const _PreferencesTab({required this.auth});

  final AuthState auth;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: <Widget>[
        SectionCard(
          titleKey: 'common.profile',
          child: Wrap(
            spacing: 24,
            runSpacing: 12,
            children: <Widget>[
              _value(context, 'common.name', auth.user?.displayName),
              _value(context, 'login.email', auth.user?.email),
              _value(context, 'common.details', auth.user?.jobTitle),
              _value(context, 'common.company', auth.company?.displayName),
              _value(context, 'common.currency', auth.company?.baseCurrencyCode),
              _value(context, 'settings.roles', auth.roles.map((RoleRef role) => role.name).join(', ')),
              _value(context, 'common.status', auth.dataScope),
            ],
          ),
        ),
        const SizedBox(height: 12),
        SectionCard(
          titleKey: 'settings.preferences',
          child: Column(
            children: <Widget>[
              SwitchListTile(
                value: ref.watch(localeProvider).languageCode == 'ar',
                title: Text(context.tr('common.language')),
                subtitle: Text(context.tr(localeProvider == null ? 'common.language' : 'login.language_toggle')),
                onChanged: (bool _) => ref.read(localeProvider.notifier).toggle(),
              ),
              SwitchListTile(
                value: ref.watch(themeModeProvider) == ThemeMode.dark,
                title: Text(context.tr('common.theme')),
                onChanged: (bool _) => ref.read(themeModeProvider.notifier).toggle(),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        SectionCard(
          titleKey: 'settings.organisation',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              for (final LookupRef branch in auth.branches)
                ListTile(dense: true, leading: const Icon(Icons.account_tree_outlined, size: 18), title: Text(branch.name)),
              for (final LookupRef warehouse in auth.warehouses)
                ListTile(dense: true, leading: const Icon(Icons.warehouse_outlined, size: 18), title: Text(warehouse.name)),
            ],
          ),
        ),
      ],
    );
  }

  Widget _value(BuildContext context, String labelKey, String? value) => SizedBox(
        width: 260,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(context.tr(labelKey), style: Theme.of(context).textTheme.labelSmall),
            Text(value ?? context.tr('common.empty_value')),
          ],
        ),
      );
}

class _PasswordTab extends ConsumerStatefulWidget {
  const _PasswordTab();

  @override
  ConsumerState<_PasswordTab> createState() => _PasswordTabState();
}

class _PasswordTabState extends ConsumerState<_PasswordTab> {
  final TextEditingController _current = TextEditingController();
  final TextEditingController _next = TextEditingController();
  final TextEditingController _confirm = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _current.dispose();
    _next.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_next.text != _confirm.text) {
      context.showError(StateError(context.tr('password.mismatch')));
      return;
    }
    setState(() => _busy = true);
    try {
      await ref.read(authProvider.notifier).changePassword(
            currentPassword: _current.text,
            newPassword: _next.text,
          );
      if (mounted) {
        context.showSuccess('password.changed');
        _current.clear();
        _next.clear();
        _confirm.clear();
      }
    } catch (error) {
      if (mounted) context.showError(error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Center(
      child: SizedBox(
        width: 420,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            TextField(
              controller: _current,
              obscureText: true,
              decoration: InputDecoration(labelText: context.tr('password.current')),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _next,
              obscureText: true,
              decoration: InputDecoration(labelText: context.tr('password.new')),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _confirm,
              obscureText: true,
              decoration: InputDecoration(labelText: context.tr('password.confirm')),
            ),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: _busy ? null : _submit,
              icon: const Icon(Icons.lock_reset, size: 18),
              label: Text(context.tr('password.change')),
            ),
          ],
        ),
      ),
    );
  }
}

class _SessionsTab extends ConsumerWidget {
  const _SessionsTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final String locale = Localizations.localeOf(context).languageCode;
    final String? currentSession = ref.watch(authProvider).sessionId;
    return Padding(
      padding: const EdgeInsets.all(20),
      child: AsyncView<List<Map<String, dynamic>>>(
        value: ref.watch(sessionsProvider),
        onRetry: () => ref.invalidate(sessionsProvider),
        isEmpty: (List<Map<String, dynamic>> data) => data.isEmpty,
        builder: (List<Map<String, dynamic>> sessions) => ListView.builder(
          itemCount: sessions.length,
          itemBuilder: (BuildContext context, int index) {
            final Map<String, dynamic> session = sessions[index];
            final bool isCurrent = '${session['id']}' == currentSession;
            return Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                leading: Icon(session['revoked_at'] == null ? Icons.devices_other : Icons.block_outlined),
                title: Text('${session['device_name'] ?? session['user_agent'] ?? session['id']}'),
                subtitle: Text(
                  '${context.tr('session.ip')}: ${session['ip_address'] ?? '-'} · '
                  '${context.tr('session.last_seen')}: ${Fmt.relative(session['last_seen_at'] ?? session['created_at'], locale: locale)}',
                ),
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    if (isCurrent) CountChip(context.tr('session.current'), icon: Icons.check),
                    if (!isCurrent && session['revoked_at'] == null)
                      TextButton(
                        onPressed: () async {
                          if (!await confirmDialog(context, confirmKey: 'session.revoke')) return;
                          await ref.read(apiProvider).remove('/auth/sessions', '${session['id']}');
                          ref.invalidate(sessionsProvider);
                        },
                        child: Text(context.tr('session.revoke')),
                      ),
                  ],
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}

class _ModulesTab extends ConsumerWidget {
  const _ModulesTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: AsyncView<List<Map<String, dynamic>>>(
        value: ref.watch(companyModulesProvider),
        onRetry: () => ref.invalidate(companyModulesProvider),
        isEmpty: (List<Map<String, dynamic>> data) => data.isEmpty,
        builder: (List<Map<String, dynamic>> modules) => Wrap(
          spacing: 10,
          runSpacing: 10,
          children: <Widget>[
            for (final Map<String, dynamic> module in modules)
              SizedBox(
                width: 260,
                child: Card(
                  child: SwitchListTile(
                    value: Fmt.toBool(module['is_enabled'] ?? module['enabled'] ?? true),
                    title: Text('${module['name'] ?? module['code']}'),
                    subtitle: Text('${module['code'] ?? ''}'),
                    onChanged: (bool value) async {
                      try {
                        await ref.read(apiProvider).create(
                              '/admin/companies/${ref.read(authProvider).company?.id}/modules',
                              <String, dynamic>{'code': '${module['code']}', 'is_enabled': value},
                            );
                        ref.invalidate(companyModulesProvider);
                      } catch (error) {
                        if (context.mounted) context.showError(error);
                      }
                    },
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Approval inbox: documents waiting for the signed-in user.
class ApprovalsPage extends ConsumerStatefulWidget {
  const ApprovalsPage({super.key});

  @override
  ConsumerState<ApprovalsPage> createState() => _ApprovalsPageState();
}

class _ApprovalsPageState extends ConsumerState<ApprovalsPage> {
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
          await ref.read(apiProvider).collection('/workflow/my-approvals', query: <String, dynamic>{'page_size': 50});
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

  Future<void> _decide(Map<String, dynamic> item, String decision) async {
    final String? reason = decision == 'reject' ? await reasonDialog(context, titleKey: 'action.reject') : null;
    if (decision == 'reject' && reason == null) return;
    try {
      await ref.read(apiProvider).create('/workflow/instances/${item['id']}/decide', <String, dynamic>{
        'decision': decision,
        if (reason != null) 'comment': reason,
      });
      await _load();
      if (mounted) context.showSuccess('common.saved');
    } catch (error) {
      if (mounted) context.showError(error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final String locale = Localizations.localeOf(context).languageCode;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        PageHeader(
          titleKey: 'workflow.my_approvals',
          breadcrumbs: <String>['nav.workflow', 'workflow.my_approvals'],
          actions: <Widget>[IconButton(onPressed: _load, icon: const Icon(Icons.refresh))],
        ),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: _loading
                ? const LoadingState()
                : _error != null
                    ? ErrorState(error: _error!, onRetry: _load)
                    : _items.isEmpty
                        ? const EmptyState()
                        : ListView.builder(
                            itemCount: _items.length,
                            itemBuilder: (BuildContext context, int index) {
                              final Map<String, dynamic> item = _items[index];
                              return Card(
                                margin: const EdgeInsets.only(bottom: 8),
                                child: ListTile(
                                  leading: const Icon(Icons.approval_outlined),
                                  title: Text('${item['document_no'] ?? item['title'] ?? item['id']}'),
                                  subtitle: Text(
                                    '${item['document_type'] ?? ''} · ${Fmt.date(item['created_at'], locale: locale)}'
                                    '${item['amount'] == null ? '' : ' · ${Fmt.money(item['amount'])}'}',
                                  ),
                                  trailing: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: <Widget>[
                                      TextButton(
                                        onPressed: () => _decide(item, 'reject'),
                                        child: Text(context.tr('action.reject')),
                                      ),
                                      FilledButton(
                                        onPressed: () => _decide(item, 'approve'),
                                        child: Text(context.tr('action.approve')),
                                      ),
                                    ],
                                  ),
                                ),
                              );
                            },
                          ),
          ),
        ),
      ],
    );
  }
}
