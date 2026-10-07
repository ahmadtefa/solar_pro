import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/l10n/app_strings.dart';
import '../../../core/models/auth_models.dart';
import '../../../core/providers.dart';
import '../../auth/state/auth_controller.dart';
import '../../modules/module_registry.dart';
import '../../notifications/presentation/notification_center.dart';
import 'global_search.dart';

/// Application chrome: collapsible sidebar, top bar with search, alerts and the
/// user menu. The sidebar is built from [ModuleRegistry] and filtered by the
/// permissions of the signed-in user.
class AppShell extends ConsumerStatefulWidget {
  const AppShell({required this.child, super.key});

  final Widget child;

  @override
  ConsumerState<AppShell> createState() => _AppShellState();
}

class _AppShellState extends ConsumerState<AppShell> {
  bool _collapsed = false;

  @override
  Widget build(BuildContext context) {
    final AuthState auth = ref.watch(authProvider);
    final List<NavGroup> groups = ModuleRegistry.navigation();
    final double width = _collapsed ? 72 : 268;

    return Scaffold(
      body: Row(
        children: <Widget>[
          AnimatedContainer(
            duration: const Duration(milliseconds: 150),
            width: width,
            child: _Sidebar(
              groups: groups,
              auth: auth,
              collapsed: _collapsed,
              onToggle: () => setState(() => _collapsed = !_collapsed),
            ),
          ),
          const VerticalDivider(width: 1),
          Expanded(
            child: Column(
              children: <Widget>[
                _TopBar(auth: auth),
                const Divider(height: 1),
                Expanded(child: widget.child),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Sidebar extends ConsumerWidget {
  const _Sidebar({required this.groups, required this.auth, required this.collapsed, required this.onToggle});

  final List<NavGroup> groups;
  final AuthState auth;
  final bool collapsed;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ThemeData theme = Theme.of(context);
    final String location = GoRouterState.of(context).matchedLocation;

    return Container(
      color: theme.colorScheme.surfaceContainerLowest,
      child: Column(
        children: <Widget>[
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 14, 8, 10),
            child: Row(
              children: <Widget>[
                Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primary,
                    borderRadius: BorderRadius.circular(9),
                  ),
                  alignment: Alignment.center,
                  child: Text(
                    'K',
                    style: TextStyle(color: theme.colorScheme.onPrimary, fontWeight: FontWeight.bold, fontSize: 18),
                  ),
                ),
                if (!collapsed) ...<Widget>[
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(context.tr('app.name'), style: theme.textTheme.titleMedium),
                        Text(
                          auth.company?.displayName ?? context.tr('app.tagline'),
                          style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                ],
                IconButton(
                  tooltip: context.tr('common.filters'),
                  onPressed: onToggle,
                  icon: Icon(collapsed ? Icons.chevron_right : Icons.chevron_left, size: 18),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(vertical: 6),
              children: <Widget>[
                for (final NavGroup group in groups)
                  if (_visible(group).isNotEmpty) ...<Widget>[
                    if (!collapsed)
                      Padding(
                        padding: const EdgeInsets.fromLTRB(16, 14, 12, 4),
                        child: Text(
                          context.tr(group.labelKey).toUpperCase(),
                          style: theme.textTheme.labelSmall?.copyWith(
                            color: theme.colorScheme.outline,
                            letterSpacing: 0.8,
                          ),
                        ),
                      ),
                    for (final NavItem item in _visible(group))
                      _SidebarTile(
                        item: item,
                        collapsed: collapsed,
                        selected: location == item.route || location.startsWith('${item.route}/'),
                      ),
                  ],
              ],
            ),
          ),
          const Divider(height: 1),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
            child: Text(
              'v${const String.fromEnvironment('APP_VERSION', defaultValue: '1.0.0')}',
              style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.outline),
            ),
          ),
        ],
      ),
    );
  }

  List<NavItem> _visible(NavGroup group) => group.items
      .where((NavItem item) => auth.can(item.permission) && (item.module == null || auth.hasModule(item.module!)))
      .toList(growable: false);
}

class _SidebarTile extends StatelessWidget {
  const _SidebarTile({required this.item, required this.collapsed, required this.selected});

  final NavItem item;
  final bool collapsed;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: collapsed ? context.tr(item.labelKey) : '',
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
        child: ListTile(
          dense: true,
          selected: selected,
          selectedTileColor: Theme.of(context).colorScheme.primaryContainer.withValues(alpha: 0.4),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          leading: Icon(item.icon, size: 20),
          title: collapsed
              ? null
              : Text(
                  context.tr(item.labelKey),
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontWeight: selected ? FontWeight.w600 : FontWeight.w400, fontSize: 13.5),
                ),
          onTap: () => context.go(item.route),
        ),
      ),
    );
  }
}

class _TopBar extends ConsumerWidget {
  const _TopBar({required this.auth});

  final AuthState auth;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ThemeData theme = Theme.of(context);
    return Container(
      height: 58,
      color: theme.colorScheme.surface,
      padding: const EdgeInsets.symmetric(horizontal: 12),
      child: Row(
        children: <Widget>[
          Expanded(
            child: InkWell(
              borderRadius: BorderRadius.circular(10),
              onTap: () => showGlobalSearch(context),
              child: Container(
                height: 38,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: theme.colorScheme.outlineVariant),
                  color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.25),
                ),
                child: Row(
                  children: <Widget>[
                    Icon(Icons.search, size: 18, color: theme.colorScheme.outline),
                    const SizedBox(width: 8),
                    Text(
                      context.tr('search.hint'),
                      style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.outline),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),
          if (auth.companies.length > 1)
            Padding(
              padding: const EdgeInsetsDirectional.only(end: 8),
              child: DropdownButton<String>(
                value: auth.company?.id,
                underline: const SizedBox.shrink(),
                items: <DropdownMenuItem<String>>[
                  for (final CompanyRef company in auth.companies)
                    DropdownMenuItem<String>(value: company.id, child: Text(company.displayName)),
                ],
                onChanged: (String? companyId) async {
                  if (companyId == null || companyId == auth.company?.id) return;
                  await ref.read(authProvider.notifier).switchCompany(companyId);
                },
              ),
            ),
          IconButton(
            tooltip: context.tr('common.language'),
            onPressed: () => ref.read(localeProvider.notifier).toggle(),
            icon: const Icon(Icons.translate),
          ),
          IconButton(
            tooltip: context.tr('common.theme'),
            onPressed: () => ref.read(themeModeProvider.notifier).toggle(),
            icon: Icon(theme.brightness == Brightness.dark ? Icons.light_mode_outlined : Icons.dark_mode_outlined),
          ),
          const NotificationBell(),
          const SizedBox(width: 4),
          PopupMenuButton<String>(
            tooltip: context.tr('common.my_account'),
            onSelected: (String value) async {
              switch (value) {
                case 'profile':
                  context.go('/settings');
                case 'sessions':
                  context.go('/settings');
                case 'logout':
                  await ref.read(authProvider.notifier).logout();
              }
            },
            itemBuilder: (BuildContext context) => <PopupMenuEntry<String>>[
              PopupMenuItem<String>(value: 'profile', child: Text(context.tr('common.profile'))),
              PopupMenuItem<String>(value: 'sessions', child: Text(context.tr('session.title'))),
              const PopupMenuDivider(),
              PopupMenuItem<String>(value: 'logout', child: Text(context.tr('common.logout'))),
            ],
            child: CircleAvatar(
              radius: 17,
              backgroundColor: theme.colorScheme.primaryContainer,
              child: Text(
                auth.user?.initials ?? '?',
                style: TextStyle(fontSize: 12, color: theme.colorScheme.onPrimaryContainer),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
