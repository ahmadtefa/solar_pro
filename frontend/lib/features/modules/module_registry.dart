import 'package:flutter/material.dart';

import '../../shared/resource/document_config.dart';
import '../../shared/resource/resource_config.dart';
import 'business_configs.dart';
import 'document_configs.dart';
import 'platform_configs.dart';

/// One link in the sidebar.
class NavItem {
  const NavItem({
    required this.labelKey,
    required this.icon,
    required this.route,
    required this.permission,
    this.module,
  });

  final String labelKey;
  final IconData icon;
  final String route;
  final String permission;

  /// Module code from the company's module activation list, when relevant.
  final String? module;
}

class NavGroup {
  const NavGroup({required this.labelKey, required this.items});

  final String labelKey;
  final List<NavItem> items;
}

/// Single source of truth for navigation and for the generic screens.
///
/// Adding a module means adding a config here: the router, the sidebar and the
/// CRUD screens all read from this registry, so nothing can drift apart.
class ModuleRegistry {
  const ModuleRegistry._();

  static final Map<String, ResourceConfig> resources = <String, ResourceConfig>{
    ...PlatformConfigs.all(),
    ...BusinessConfigs.all(),
  };

  static final Map<String, DocumentConfig> documents = DocumentConfigs.all();

  static ResourceConfig? resource(String key) => resources[key];

  static DocumentConfig? document(String key) => documents[key];

  static const String resourcePrefix = '/r';
  static const String documentPrefix = '/d';

  static String resourceRoute(String key) => '$resourcePrefix/$key';

  static String documentRoute(String key) => '$documentPrefix/$key';

  static NavItem _resourceItem(String key) {
    final ResourceConfig config = resources[key]!;
    return NavItem(
      labelKey: config.nameKey,
      icon: config.icon ?? Icons.table_rows_outlined,
      route: resourceRoute(key),
      permission: config.viewPermission,
    );
  }

  static NavItem _documentItem(String key) {
    final DocumentConfig config = documents[key]!;
    return NavItem(
      labelKey: config.nameKey,
      icon: config.icon ?? Icons.description_outlined,
      route: documentRoute(key),
      permission: config.viewPermission,
    );
  }

  /// The sidebar tree, grouped exactly like the ERP departments.
  static List<NavGroup> navigation() => <NavGroup>[
        const NavGroup(
          labelKey: 'group.operations',
          items: <NavItem>[
            NavItem(labelKey: 'nav.dashboard', icon: Icons.dashboard_outlined, route: '/dashboard', permission: 'core.dashboard.view'),
            NavItem(labelKey: 'nav.pos', icon: Icons.point_of_sale, route: '/pos', permission: 'sales.pos_terminal.view', module: 'sales'),
          ],
        ),
        NavGroup(
          labelKey: 'nav.sales',
          items: <NavItem>[
            _documentItem('quotations'),
            _documentItem('sales-orders'),
            _documentItem('deliveries'),
            _documentItem('sales-invoices'),
            _documentItem('credit-notes'),
            _resourceItem('customers'),
            _resourceItem('pos-terminal-master'),
            _resourceItem('sales-commissions'),
          ],
        ),
        NavGroup(
          labelKey: 'nav.purchasing',
          items: <NavItem>[
            _documentItem('purchase-requests'),
            _documentItem('rfqs'),
            _documentItem('supplier-quotations'),
            _documentItem('purchase-orders'),
            _documentItem('goods-receipts'),
            _documentItem('purchase-invoices'),
            _documentItem('debit-notes'),
            _resourceItem('supplier-products'),
            _resourceItem('supplier-groups'),
            _resourceItem('supplier-evaluations'),
          ],
        ),
        NavGroup(
          labelKey: 'nav.crm',
          items: <NavItem>[
            _resourceItem('leads'),
            _resourceItem('opportunities'),
            _resourceItem('activities'),
            _resourceItem('contacts'),
            _resourceItem('customer-groups'),
            _resourceItem('lead-sources'),
            _resourceItem('pipeline-stages'),
            _resourceItem('sales-targets'),
          ],
        ),
        NavGroup(
          labelKey: 'nav.inventory',
          items: <NavItem>[
            _resourceItem('products'),
            _resourceItem('product-categories'),
            _resourceItem('warehouses'),
            _resourceItem('price-lists'),
            _resourceItem('product-barcodes'),
            _resourceItem('product-units'),
            _resourceItem('reorder-rules'),
            _resourceItem('batches'),
            _resourceItem('serials'),
            _resourceItem('stock-balances'),
            _resourceItem('stock-ledger'),
            _documentItem('stock-adjustments'),
            _documentItem('stock-transfers'),
            _documentItem('stock-counts'),
          ],
        ),
        NavGroup(
          labelKey: 'nav.accounting',
          items: <NavItem>[
            _documentItem('journal-entries'),
            _resourceItem('accounts'),
            _resourceItem('posting-rules'),
            _resourceItem('budgets'),
            _resourceItem('fiscal-years'),
            _resourceItem('fiscal-periods'),
          ],
        ),
        NavGroup(
          labelKey: 'nav.treasury',
          items: <NavItem>[
            _documentItem('payments'),
            _documentItem('treasury-transfers'),
            _resourceItem('cash-accounts'),
            _resourceItem('bank-accounts'),
            _resourceItem('cheques'),
          ],
        ),
        NavGroup(
          labelKey: 'nav.expenses',
          items: <NavItem>[
            _documentItem('expenses'),
            _documentItem('expense-claims'),
            _documentItem('advances'),
            _resourceItem('expense-categories'),
          ],
        ),
        NavGroup(
          labelKey: 'nav.assets',
          items: <NavItem>[
            _resourceItem('assets'),
            _resourceItem('asset-categories'),
            _resourceItem('asset-maintenance'),
            _documentItem('asset-transfers'),
            _documentItem('asset-disposals'),
          ],
        ),
        NavGroup(
          labelKey: 'nav.hr',
          items: <NavItem>[
            _resourceItem('employees'),
            _resourceItem('positions'),
            _resourceItem('employee-contracts'),
            _resourceItem('attendance-records'),
            _resourceItem('shifts'),
            _resourceItem('shift-assignments'),
            _resourceItem('holidays'),
            _resourceItem('leave-types'),
            _resourceItem('leave-balances'),
            _resourceItem('loans'),
            _documentItem('leave-requests'),
          ],
        ),
        NavGroup(
          labelKey: 'nav.project',
          items: <NavItem>[
            _resourceItem('projects'),
            _resourceItem('project-phases'),
            _resourceItem('project-tasks'),
            _resourceItem('project-resources'),
            _documentItem('timesheets'),
          ],
        ),
        NavGroup(
          labelKey: 'nav.manufacturing',
          items: <NavItem>[
            _documentItem('production-orders'),
            _resourceItem('boms'),
            _resourceItem('routings'),
            _resourceItem('work-centers'),
          ],
        ),
        NavGroup(
          labelKey: 'nav.service',
          items: <NavItem>[
            _documentItem('work-orders'),
            _documentItem('service-contracts'),
            _resourceItem('warranties'),
            _resourceItem('technician-schedules'),
          ],
        ),
        NavGroup(
          labelKey: 'nav.reports',
          items: const <NavItem>[
            NavItem(labelKey: 'reports.title', icon: Icons.analytics_outlined, route: '/reports', permission: 'core.report.view'),
            NavItem(labelKey: 'reports.saved', icon: Icons.bookmark_border, route: '/reports/saved', permission: 'core.saved_report.view'),
          ],
        ),
        NavGroup(
          labelKey: 'nav.workflow',
          items: const <NavItem>[
            NavItem(labelKey: 'workflow.my_approvals', icon: Icons.approval_outlined, route: '/approvals', permission: 'workflow.approval.view'),
          ],
        ),
        NavGroup(
          labelKey: 'group.platform',
          items: <NavItem>[
            NavItem(labelKey: 'nav.settings', icon: Icons.tune, route: '/settings', permission: 'core.system_setting.view'),
            NavItem(labelKey: 'nav.audit', icon: Icons.history, route: resourceRoute('audit-logs'), permission: 'core.audit_log.view'),
            NavItem(labelKey: 'data.import', icon: Icons.upload_file, route: '/data-tools', permission: 'core.import_job.view'),
            NavItem(labelKey: 'data.backup', icon: Icons.backup_outlined, route: '/backup', permission: 'core.backup.view'),
            _resourceItem('users'),
            _resourceItem('roles'),
            _resourceItem('companies'),
            _resourceItem('branches'),
            _resourceItem('departments'),
            _resourceItem('divisions'),
            _resourceItem('cost-centers'),
            _resourceItem('taxes'),
            _resourceItem('payment-terms'),
            _resourceItem('currencies'),
            _resourceItem('exchange-rates'),
            _resourceItem('units'),
            _resourceItem('unit-groups'),
            _resourceItem('unit-conversions'),
            _resourceItem('document-types'),
            _resourceItem('numbering'),
            _resourceItem('countries'),
            _resourceItem('cities'),
            _resourceItem('addresses'),
            _resourceItem('settings'),
          ],
        ),
      ];
}
