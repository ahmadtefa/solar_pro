import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/presentation/login_page.dart';
import '../../features/dashboard/presentation/dashboard_page.dart';
import '../../features/data_tools/presentation/data_tools_page.dart';
import '../../features/modules/module_registry.dart';
import '../../features/notifications/presentation/notification_center.dart';
import '../../features/pos/presentation/pos_page.dart';
import '../../features/reports/presentation/reports_page.dart';
import '../../features/settings/presentation/settings_page.dart';
import '../../features/shell/presentation/app_shell.dart';
import '../l10n/app_strings.dart';
import '../models/auth_models.dart';
import '../providers.dart';
import '../../shared/resource/document_config.dart';
import '../../shared/resource/document_page.dart';
import '../../shared/resource/resource_config.dart';
import '../../shared/resource/resource_page.dart';

/// Bridges Riverpod state changes into the router's `refreshListenable`.
class _AuthRefresh extends ChangeNotifier {
  _AuthRefresh() {
    addListener(() {});
  }

  void ping() => notifyListeners();
}

final routerProvider = Provider<GoRouter>((Ref ref) {
  final _AuthRefresh refresh = _AuthRefresh();
  ref.listen<AuthState>(authProvider, (AuthState? previous, AuthState next) {
    if (previous?.accessToken != next.accessToken || previous?.permissions != next.permissions) {
      refresh.ping();
    }
  });
  ref.onDispose(refresh.dispose);

  return GoRouter(
    initialLocation: '/dashboard',
    refreshListenable: refresh,
    redirect: (BuildContext context, GoRouterState state) {
      final AuthState auth = ref.read(authProvider);
      final String location = state.matchedLocation;
      final bool loggingIn = location == '/login';
      if (!auth.isAuthenticated) {
        return loggingIn ? null : '/login';
      }
      if (loggingIn) return '/dashboard';
      final bool allowed = _allowed(location, auth);
      return allowed ? null : '/dashboard';
    },
    errorBuilder: (BuildContext context, GoRouterState state) => Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const Icon(Icons.explore_off_outlined, size: 44),
            const SizedBox(height: 12),
            Text(context.tr('error.not_found')),
            const SizedBox(height: 12),
            FilledButton(onPressed: () => context.go('/dashboard'), child: Text(context.tr('nav.dashboard'))),
          ],
        ),
      ),
    ),
    routes: <RouteBase>[
      GoRoute(path: '/login', builder: (BuildContext context, GoRouterState state) => const LoginPage()),
      ShellRoute(
        builder: (BuildContext context, GoRouterState state, Widget child) => AppShell(child: child),
        routes: <RouteBase>[
          GoRoute(path: '/dashboard', builder: (BuildContext context, GoRouterState state) => const DashboardPage()),
          GoRoute(path: '/pos', builder: (BuildContext context, GoRouterState state) => const PosPage()),
          GoRoute(
            path: '/reports',
            builder: (BuildContext context, GoRouterState state) => const ReportsPage(),
            routes: <RouteBase>[
              GoRoute(
                path: 'saved',
                builder: (BuildContext context, GoRouterState state) => const ReportsPage(savedOnly: true),
              ),
            ],
          ),
          GoRoute(path: '/approvals', builder: (BuildContext context, GoRouterState state) => const ApprovalsPage()),
          GoRoute(path: '/settings', builder: (BuildContext context, GoRouterState state) => const SettingsPage()),
          GoRoute(path: '/data-tools', builder: (BuildContext context, GoRouterState state) => const DataImportPage()),
          GoRoute(path: '/backup', builder: (BuildContext context, GoRouterState state) => const BackupPage()),
          GoRoute(path: '/export', builder: (BuildContext context, GoRouterState state) => const DataExportPage()),
          GoRoute(
            path: '/notifications',
            builder: (BuildContext context, GoRouterState state) => const NotificationsPage(),
          ),
          GoRoute(
            path: '${ModuleRegistry.resourcePrefix}/:key',
            builder: (BuildContext context, GoRouterState state) {
              final ResourceConfig? config = ModuleRegistry.resource(state.pathParameters['key'] ?? '');
              if (config == null) return const _MissingConfig();
              return ResourcePage(config: config);
            },
          ),
          GoRoute(
            path: '${ModuleRegistry.documentPrefix}/:key',
            builder: (BuildContext context, GoRouterState state) {
              final DocumentConfig? config = ModuleRegistry.document(state.pathParameters['key'] ?? '');
              if (config == null) return const _MissingConfig();
              return DocumentPage(config: config);
            },
          ),
        ],
      ),
    ],
  );
});

bool _allowed(String location, AuthState auth) {
  if (!location.startsWith('${ModuleRegistry.resourcePrefix}/') && !location.startsWith('${ModuleRegistry.documentPrefix}/')) {
    return true;
  }
  final String key = location.split('/').last;
  final ResourceConfig? resource = ModuleRegistry.resource(key);
  if (resource != null) return auth.can(resource.viewPermission);
  final DocumentConfig? document = ModuleRegistry.document(key);
  if (document != null) return auth.can(document.viewPermission);
  return false;
}

class _MissingConfig extends StatelessWidget {
  const _MissingConfig();

  @override
  Widget build(BuildContext context) => Scaffold(
        body: Center(child: Text(context.tr('error.not_found'))),
      );
}
