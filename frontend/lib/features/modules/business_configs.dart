import 'package:flutter/material.dart';

import '../../shared/resource/resource_config.dart';

/// Master-data and register screens for the commercial, inventory, finance and
/// operations modules. Keys are the database column names returned by the API.
class BusinessConfigs {
  const BusinessConfigs._();

  static Map<String, ResourceConfig> all() => <String, ResourceConfig>{
        // CRM
        'customers': customers,
        'customer-groups': customerGroups,
        'contacts': contacts,
        'leads': leads,
        'lead-sources': leadSources,
        'pipeline-stages': pipelineStages,
        'opportunities': opportunities,
        'activities': activities,
        'sales-targets': salesTargets,
        // Suppliers
        'supplier-groups': supplierGroups,
        'supplier-products': supplierProducts,
        'supplier-evaluations': supplierEvaluations,
        // Catalogue and inventory
        'products': products,
        'product-categories': productCategories,
        'brands': brands,
        'warehouses': warehouses,
        'price-lists': priceLists,
        'product-barcodes': productBarcodes,
        'product-units': productUnits,
        'reorder-rules': reorderRules,
        'batches': batches,
        'serials': serials,
        'stock-balances': stockBalances,
        'stock-ledger': stockLedger,
        // Finance
        'accounts': accounts,
        'budgets': budgets,
        'posting-rules': postingRules,
        'cash-accounts': cashAccounts,
        'bank-accounts': bankAccounts,
        'cheques': cheques,
        'expense-categories': expenseCategories,
        'asset-categories': assetCategories,
        'assets': assets,
        'asset-maintenance': assetMaintenance,
        // People and projects
        'employees': employees,
        'positions': positions,
        'employee-contracts': employeeContracts,
        'attendance-records': attendanceRecords,
        'shifts': shifts,
        'shift-assignments': shiftAssignments,
        'holidays': holidays,
        'leave-types': leaveTypes,
        'leave-balances': leaveBalances,
        'loans': loans,
        'projects': projects,
        'project-phases': projectPhases,
        'project-tasks': projectTasks,
        'project-resources': projectResources,
        'boms': boms,
        'routings': routings,
        'work-centers': workCenters,
        'contracts': contractsMasterExtra,
        'warranties': warranties,
        'technician-schedules': technicianSchedules,
        'pos-terminal-master': posTerminals,
        'sales-commissions': commissions,
      };

  // ------------------------------------------------------------------- CRM
  static const ResourceConfig customers = ResourceConfig(
    nameKey: 'common.customer',
    path: '/customers',
    permissionPrefix: 'crm.customer',
    icon: Icons.storefront_outlined,
    breadcrumbs: <String>['nav.crm', 'common.customer'],
    exportEntity: 'customers',
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 110, emphasize: true),
      ColumnSpec('name', 'common.name', width: 220),
      ColumnSpec('name_ar', 'common.name_ar', width: 200),
      ColumnSpec('phone', 'common.reference', width: 140),
      ColumnSpec('email', 'login.email', width: 190),
      ColumnSpec('credit_limit', 'common.total', type: FieldType.decimal, width: 130, align: MainAxisAlignment.end),
      ColumnSpec('is_credit_hold', 'status.pending', type: FieldType.boolean, width: 110),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    filters: <FilterSpec>[
      FilterSpec(key: 'is_active', labelKey: 'common.active', options: <DropdownOption>[
        DropdownOption('true', 'common.active'),
        DropdownOption('false', 'common.inactive'),
      ]),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'customer_group_id', labelKey: 'nav.crm', type: FieldType.reference, optionsKey: 'list:/customer-groups#name'),
      FieldSpec(key: 'email', labelKey: 'login.email'),
      FieldSpec(key: 'phone', labelKey: 'common.reference'),
      FieldSpec(key: 'mobile', labelKey: 'common.reference'),
      FieldSpec(key: 'tax_registration_number', labelKey: 'reports.tax'),
      FieldSpec(key: 'country_code', labelKey: 'common.country', type: FieldType.reference, optionsKey: 'lookup:countries'),
      FieldSpec(key: 'city', labelKey: 'common.city'),
      FieldSpec(key: 'address_line1', labelKey: 'common.description', span: 2),
      FieldSpec(key: 'credit_limit', labelKey: 'common.total', type: FieldType.decimal),
      FieldSpec(key: 'credit_days', labelKey: 'common.quantity', type: FieldType.integer),
      FieldSpec(key: 'payment_term_id', labelKey: 'nav.master_data', type: FieldType.reference, optionsKey: 'lookup:payment-terms'),
      FieldSpec(key: 'price_list_id', labelKey: 'settings.finance', type: FieldType.reference, optionsKey: 'list:/price-lists#name'),
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
  );

  static const ResourceConfig customerGroups = ResourceConfig(
    nameKey: 'nav.crm',
    path: '/customer-groups',
    permissionPrefix: 'crm.customer_group',
    icon: Icons.groups_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 120, emphasize: true),
      ColumnSpec('name', 'common.name', width: 240),
      ColumnSpec('name_ar', 'common.name_ar', width: 200),
      ColumnSpec('discount_percent', 'common.discount', type: FieldType.decimal, width: 120),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'discount_percent', labelKey: 'common.discount', type: FieldType.decimal),
    ],
  );

  static const ResourceConfig contacts = ResourceConfig(
    nameKey: 'nav.crm',
    path: '/contacts',
    permissionPrefix: 'crm.contact',
    icon: Icons.contact_page_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('first_name', 'common.name', width: 160, emphasize: true),
      ColumnSpec('last_name', 'common.name', width: 160),
      ColumnSpec('party_type', 'common.party', width: 120),
      ColumnSpec('email', 'login.email', width: 200),
      ColumnSpec('phone', 'common.reference', width: 140),
      ColumnSpec('is_primary', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'first_name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'last_name', labelKey: 'common.name'),
      FieldSpec(
        key: 'party_type',
        labelKey: 'common.party',
        type: FieldType.select,
        options: <DropdownOption>[
          DropdownOption('customer', 'common.customer'),
          DropdownOption('supplier', 'common.supplier'),
          DropdownOption('lead', 'nav.crm'),
        ],
      ),
      FieldSpec(key: 'party_id', labelKey: 'common.party'),
      FieldSpec(key: 'email', labelKey: 'login.email'),
      FieldSpec(key: 'phone', labelKey: 'common.reference'),
      FieldSpec(key: 'mobile', labelKey: 'common.reference'),
      FieldSpec(key: 'job_title', labelKey: 'common.details'),
      FieldSpec(key: 'is_primary', labelKey: 'common.active', type: FieldType.boolean),
    ],
  );

  static const ResourceConfig leads = ResourceConfig(
    nameKey: 'nav.crm',
    path: '/leads',
    permissionPrefix: 'crm.lead',
    icon: Icons.person_search_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('lead_no', 'common.code', width: 120, emphasize: true),
      ColumnSpec('company_name', 'common.name', width: 200),
      ColumnSpec('contact_name', 'common.name', width: 170),
      ColumnSpec('status', 'common.status', isStatus: true, width: 120),
      ColumnSpec('priority', 'common.status', width: 100),
      ColumnSpec('expected_value', 'common.amount', type: FieldType.decimal, width: 130, align: MainAxisAlignment.end),
      ColumnSpec('next_follow_up_at', 'common.due_date', type: FieldType.date, width: 130),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'company_name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'contact_name', labelKey: 'common.name'),
      FieldSpec(key: 'email', labelKey: 'login.email'),
      FieldSpec(key: 'phone', labelKey: 'common.reference'),
      FieldSpec(key: 'mobile', labelKey: 'common.reference'),
      FieldSpec(key: 'source_id', labelKey: 'nav.crm', type: FieldType.reference, optionsKey: 'list:/lead-sources#name'),
      FieldSpec(key: 'stage_id', labelKey: 'workflow.step', type: FieldType.reference, optionsKey: 'list:/pipeline-stages#name'),
      FieldSpec(key: 'expected_value', labelKey: 'common.amount', type: FieldType.decimal),
      FieldSpec(key: 'expected_close_date', labelKey: 'common.due_date', type: FieldType.date),
      FieldSpec(key: 'priority', labelKey: 'common.status', type: FieldType.select, options: <DropdownOption>[
        DropdownOption('low', 'common.none'),
        DropdownOption('medium', 'common.select'),
        DropdownOption('high', 'common.required'),
      ]),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
  );

  static const ResourceConfig leadSources = ResourceConfig(
    nameKey: 'nav.crm',
    path: '/lead-sources',
    permissionPrefix: 'crm.lead_source',
    icon: Icons.share_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 120, emphasize: true),
      ColumnSpec('name', 'common.name', width: 240),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig pipelineStages = ResourceConfig(
    nameKey: 'nav.crm',
    path: '/pipeline-stages',
    permissionPrefix: 'crm.pipeline_stage',
    icon: Icons.view_kanban_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 120, emphasize: true),
      ColumnSpec('name', 'common.name', width: 200),
      ColumnSpec('sequence_no', 'common.page', type: FieldType.integer, width: 100),
      ColumnSpec('probability', 'common.total', type: FieldType.decimal, width: 110),
      ColumnSpec('is_won', 'workflow.approved', type: FieldType.boolean, width: 100),
      ColumnSpec('is_lost', 'workflow.rejected', type: FieldType.boolean, width: 100),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'sequence_no', labelKey: 'common.page', type: FieldType.integer, defaultValue: 10),
      FieldSpec(key: 'probability', labelKey: 'common.total', type: FieldType.decimal),
      FieldSpec(key: 'is_won', labelKey: 'workflow.approved', type: FieldType.boolean),
      FieldSpec(key: 'is_lost', labelKey: 'workflow.rejected', type: FieldType.boolean),
    ],
  );

  static const ResourceConfig opportunities = ResourceConfig(
    nameKey: 'nav.crm',
    path: '/opportunities',
    permissionPrefix: 'crm.opportunity',
    icon: Icons.trending_up,
    columns: <ColumnSpec>[
      ColumnSpec('opportunity_no', 'common.code', width: 130, emphasize: true),
      ColumnSpec('name', 'common.name', width: 220),
      ColumnSpec('amount', 'common.amount', type: FieldType.decimal, width: 130, align: MainAxisAlignment.end),
      ColumnSpec('probability', 'common.total', type: FieldType.decimal, width: 110),
      ColumnSpec('weighted_amount', 'common.total', type: FieldType.decimal, width: 130, align: MainAxisAlignment.end),
      ColumnSpec('stage', 'common.status', width: 120),
      ColumnSpec('expected_close_date', 'common.due_date', type: FieldType.date, width: 130),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'customer_id', labelKey: 'common.customer', type: FieldType.reference, optionsKey: 'list:/customers#name'),
      FieldSpec(key: 'stage_id', labelKey: 'workflow.step', type: FieldType.reference, optionsKey: 'list:/pipeline-stages#name'),
      FieldSpec(key: 'amount', labelKey: 'common.amount', type: FieldType.decimal, required: true),
      FieldSpec(key: 'probability', labelKey: 'common.total', type: FieldType.decimal),
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'expected_close_date', labelKey: 'common.due_date', type: FieldType.date),
      FieldSpec(key: 'next_step', labelKey: 'common.details', span: 2),
    ],
  );

  static const ResourceConfig activities = ResourceConfig(
    nameKey: 'nav.crm',
    path: '/activities',
    permissionPrefix: 'crm.activity',
    icon: Icons.event_note_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('subject', 'common.name', width: 240, emphasize: true),
      ColumnSpec('activity_type', 'common.status', width: 130),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
      ColumnSpec('due_date', 'common.due_date', type: FieldType.dateTime, width: 150),
      ColumnSpec('owner_id', 'common.created_by', width: 150),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'subject', labelKey: 'common.name', required: true),
      FieldSpec(
        key: 'activity_type',
        labelKey: 'common.status',
        type: FieldType.select,
        options: <DropdownOption>[
          DropdownOption('call', 'common.reference'),
          DropdownOption('meeting', 'common.details'),
          DropdownOption('task', 'common.actions'),
          DropdownOption('email', 'login.email'),
        ],
      ),
      FieldSpec(key: 'description', labelKey: 'common.description', type: FieldType.multiline, span: 2),
      FieldSpec(key: 'due_date', labelKey: 'common.due_date', type: FieldType.date),
      FieldSpec(key: 'owner_id', labelKey: 'common.created_by'),
    ],
  );

  static const ResourceConfig salesTargets = ResourceConfig(
    nameKey: 'nav.sales',
    path: '/sales-targets',
    permissionPrefix: 'crm.sales_target',
    icon: Icons.flag_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('name', 'common.name', width: 200, emphasize: true),
      ColumnSpec('period_start', 'common.from', type: FieldType.date, width: 130),
      ColumnSpec('period_end', 'common.to', type: FieldType.date, width: 130),
      ColumnSpec('target_amount', 'common.amount', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('achieved_amount', 'common.total', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'user_id', labelKey: 'common.created_by'),
      FieldSpec(key: 'period_start', labelKey: 'common.from', type: FieldType.date, required: true),
      FieldSpec(key: 'period_end', labelKey: 'common.to', type: FieldType.date, required: true),
      FieldSpec(key: 'target_amount', labelKey: 'common.amount', type: FieldType.decimal, required: true),
    ],
  );

  // -------------------------------------------------------------- suppliers
  static const ResourceConfig supplierGroups = ResourceConfig(
    nameKey: 'nav.suppliers',
    path: '/supplier-group-master',
    permissionPrefix: 'suppliers.supplier_group',
    icon: Icons.groups_2_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 120, emphasize: true),
      ColumnSpec('name', 'common.name', width: 240),
      ColumnSpec('name_ar', 'common.name_ar', width: 200),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
    ],
  );

  static const ResourceConfig supplierProducts = ResourceConfig(
    nameKey: 'nav.suppliers',
    path: '/supplier-products',
    permissionPrefix: 'suppliers.supplier_product',
    icon: Icons.inventory_2_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('supplier_id', 'common.supplier', width: 180, emphasize: true),
      ColumnSpec('product_id', 'common.product', width: 200),
      ColumnSpec('supplier_sku', 'common.code', width: 140),
      ColumnSpec('last_price', 'common.price', type: FieldType.decimal, width: 130, align: MainAxisAlignment.end),
      ColumnSpec('lead_time_days', 'common.quantity', type: FieldType.integer, width: 120),
      ColumnSpec('is_preferred', 'common.active', type: FieldType.boolean, width: 110),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'supplier_id', labelKey: 'common.supplier', type: FieldType.reference, required: true, optionsKey: 'list:/suppliers#name'),
      FieldSpec(key: 'product_id', labelKey: 'common.product', type: FieldType.reference, required: true, optionsKey: 'list:/products#name'),
      FieldSpec(key: 'supplier_sku', labelKey: 'common.code'),
      FieldSpec(key: 'last_price', labelKey: 'common.price', type: FieldType.decimal),
      FieldSpec(key: 'lead_time_days', labelKey: 'common.quantity', type: FieldType.integer),
      FieldSpec(key: 'is_preferred', labelKey: 'common.active', type: FieldType.boolean),
    ],
  );

  static const ResourceConfig supplierEvaluations = ResourceConfig(
    nameKey: 'nav.suppliers',
    path: '/supplier-evaluations',
    permissionPrefix: 'suppliers.supplier_evaluation',
    icon: Icons.grading_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('supplier_id', 'common.supplier', width: 200, emphasize: true),
      ColumnSpec('evaluation_date', 'common.date', type: FieldType.date, width: 130),
      ColumnSpec('quality_score', 'common.total', type: FieldType.decimal, width: 120),
      ColumnSpec('delivery_score', 'common.total', type: FieldType.decimal, width: 120),
      ColumnSpec('total_score', 'reports.totals', type: FieldType.decimal, width: 120),
      ColumnSpec('grade', 'common.status', width: 100),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'supplier_id', labelKey: 'common.supplier', type: FieldType.reference, required: true, optionsKey: 'list:/suppliers#name'),
      FieldSpec(key: 'evaluation_date', labelKey: 'common.date', type: FieldType.date, required: true),
      FieldSpec(key: 'quality_score', labelKey: 'common.total', type: FieldType.decimal),
      FieldSpec(key: 'delivery_score', labelKey: 'common.total', type: FieldType.decimal),
      FieldSpec(key: 'price_score', labelKey: 'common.total', type: FieldType.decimal),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
  );

  // ------------------------------------------------------ catalogue/stock
  static const ResourceConfig products = ResourceConfig(
    nameKey: 'common.product',
    path: '/products',
    permissionPrefix: 'inventory.product',
    icon: Icons.inventory_outlined,
    breadcrumbs: <String>['nav.inventory', 'common.product'],
    exportEntity: 'products',
    columns: <ColumnSpec>[
      ColumnSpec('sku', 'common.code', width: 130, emphasize: true),
      ColumnSpec('name', 'common.name', width: 230),
      ColumnSpec('name_ar', 'common.name_ar', width: 200),
      ColumnSpec('product_type', 'common.status', width: 120),
      ColumnSpec('sales_price', 'common.price', type: FieldType.decimal, width: 120, align: MainAxisAlignment.end),
      ColumnSpec('cost_price', 'common.price', type: FieldType.decimal, width: 120, align: MainAxisAlignment.end),
      ColumnSpec('min_stock', 'dash.low_stock', type: FieldType.decimal, width: 110, align: MainAxisAlignment.end),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    filters: <FilterSpec>[
      FilterSpec(
        key: 'product_type',
        labelKey: 'common.status',
        options: <DropdownOption>[
          DropdownOption('stock', 'nav.inventory'),
          DropdownOption('service', 'nav.service'),
          DropdownOption('consumable', 'nav.inventory'),
          DropdownOption('asset', 'nav.assets'),
          DropdownOption('kit', 'nav.inventory'),
        ],
      ),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'sku', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(
        key: 'product_type',
        labelKey: 'common.status',
        type: FieldType.select,
        options: <DropdownOption>[
          DropdownOption('stock', 'nav.inventory'),
          DropdownOption('service', 'nav.service'),
          DropdownOption('consumable', 'nav.inventory'),
          DropdownOption('asset', 'nav.assets'),
          DropdownOption('kit', 'nav.inventory'),
        ],
        defaultValue: 'stock',
      ),
      FieldSpec(key: 'category_id', labelKey: 'nav.inventory', type: FieldType.reference, optionsKey: 'list:/product-categories#name'),
      FieldSpec(key: 'unit_id', labelKey: 'settings.units', type: FieldType.reference, required: true, optionsKey: 'lookup:units'),
      FieldSpec(key: 'barcode', labelKey: 'common.code'),
      FieldSpec(key: 'sales_price', labelKey: 'common.price', type: FieldType.decimal),
      FieldSpec(key: 'purchase_price', labelKey: 'common.price', type: FieldType.decimal),
      FieldSpec(key: 'cost_price', labelKey: 'common.price', type: FieldType.decimal),
      FieldSpec(key: 'sales_tax_id', labelKey: 'common.tax', type: FieldType.reference, optionsKey: 'lookup:taxes'),
      FieldSpec(key: 'purchase_tax_id', labelKey: 'common.tax', type: FieldType.reference, optionsKey: 'lookup:taxes'),
      FieldSpec(key: 'min_stock', labelKey: 'dash.low_stock', type: FieldType.decimal),
      FieldSpec(key: 'max_stock', labelKey: 'common.total', type: FieldType.decimal),
      FieldSpec(key: 'reorder_level', labelKey: 'dash.low_stock', type: FieldType.decimal),
      FieldSpec(key: 'reorder_quantity', labelKey: 'common.quantity', type: FieldType.decimal),
      FieldSpec(key: 'track_batches', labelKey: 'common.quantity', type: FieldType.boolean),
      FieldSpec(key: 'track_serials', labelKey: 'common.quantity', type: FieldType.boolean),
      FieldSpec(key: 'track_expiry', labelKey: 'common.due_date', type: FieldType.boolean),
      FieldSpec(key: 'is_sellable', labelKey: 'nav.sales', type: FieldType.boolean, defaultValue: true),
      FieldSpec(key: 'is_purchasable', labelKey: 'nav.purchasing', type: FieldType.boolean, defaultValue: true),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
      FieldSpec(key: 'description', labelKey: 'common.description', type: FieldType.multiline, span: 2),
    ],
  );

  static const ResourceConfig productCategories = ResourceConfig(
    nameKey: 'nav.inventory',
    path: '/product-categories',
    permissionPrefix: 'inventory.product_category',
    icon: Icons.account_balance_wallet_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 120, emphasize: true),
      ColumnSpec('name', 'common.name', width: 240),
      ColumnSpec('name_ar', 'common.name_ar', width: 200),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'parent_id', labelKey: 'nav.inventory', type: FieldType.reference, optionsKey: 'list:/product-categories#name'),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig brands = ResourceConfig(
    nameKey: 'nav.inventory',
    path: '/brands',
    permissionPrefix: 'inventory.brand',
    icon: Icons.workspace_premium_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 120, emphasize: true),
      ColumnSpec('name', 'common.name', width: 240),
      ColumnSpec('manufacturer', 'common.description', width: 200),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'manufacturer', labelKey: 'common.description'),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig warehouses = ResourceConfig(
    nameKey: 'common.warehouse',
    path: '/warehouses',
    permissionPrefix: 'inventory.warehouse',
    icon: Icons.warehouse_outlined,
    breadcrumbs: <String>['nav.inventory', 'common.warehouse'],
    exportEntity: 'warehouses',
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 110, emphasize: true),
      ColumnSpec('name', 'common.name', width: 220),
      ColumnSpec('name_ar', 'common.name_ar', width: 190),
      ColumnSpec('city', 'common.city', width: 140),
      ColumnSpec('allows_negative_stock', 'status.pending', type: FieldType.boolean, width: 150),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'branch_id', labelKey: 'common.branch', type: FieldType.reference, optionsKey: 'lookup:branches'),
      FieldSpec(key: 'manager_id', labelKey: 'common.employee', type: FieldType.reference, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'city', labelKey: 'common.city'),
      FieldSpec(key: 'country_code', labelKey: 'common.country', type: FieldType.reference, optionsKey: 'lookup:countries'),
      FieldSpec(key: 'address', labelKey: 'common.description', span: 2),
      FieldSpec(key: 'allows_negative_stock', labelKey: 'status.pending', type: FieldType.boolean),
      FieldSpec(key: 'is_transit', labelKey: 'common.status', type: FieldType.boolean),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig priceLists = ResourceConfig(
    nameKey: 'settings.finance',
    path: '/price-lists',
    permissionPrefix: 'inventory.price_list',
    icon: Icons.price_change_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 120, emphasize: true),
      ColumnSpec('name', 'common.name', width: 220),
      ColumnSpec('currency_code', 'common.currency', width: 110),
      ColumnSpec('valid_from', 'common.from', type: FieldType.date, width: 130),
      ColumnSpec('valid_to', 'common.to', type: FieldType.date, width: 130),
      ColumnSpec('is_default', 'common.active', type: FieldType.boolean, width: 110),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'valid_from', labelKey: 'common.from', type: FieldType.date),
      FieldSpec(key: 'valid_to', labelKey: 'common.to', type: FieldType.date),
      FieldSpec(key: 'is_default', labelKey: 'common.active', type: FieldType.boolean),
    ],
  );

  static const ResourceConfig productBarcodes = ResourceConfig(
    nameKey: 'common.product',
    path: '/product-barcodes',
    permissionPrefix: 'inventory.product_barcode',
    icon: Icons.qr_code_2,
    columns: <ColumnSpec>[
      ColumnSpec('barcode', 'common.code', width: 180, emphasize: true),
      ColumnSpec('product_id', 'common.product', width: 220),
      ColumnSpec('unit_id', 'settings.units', width: 150),
      ColumnSpec('is_primary', 'common.active', type: FieldType.boolean, width: 110),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'product_id', labelKey: 'common.product', type: FieldType.reference, required: true, optionsKey: 'list:/products#name'),
      FieldSpec(key: 'barcode', labelKey: 'common.code', required: true),
      FieldSpec(key: 'unit_id', labelKey: 'settings.units', type: FieldType.reference, optionsKey: 'lookup:units'),
      FieldSpec(key: 'is_primary', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig productUnits = ResourceConfig(
    nameKey: 'settings.units',
    path: '/product-units',
    permissionPrefix: 'inventory.product_unit',
    icon: Icons.swap_vert,
    columns: <ColumnSpec>[
      ColumnSpec('product_id', 'common.product', width: 220, emphasize: true),
      ColumnSpec('unit_id', 'settings.units', width: 160),
      ColumnSpec('conversion_factor', 'common.quantity', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('is_base', 'common.active', type: FieldType.boolean, width: 100),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'product_id', labelKey: 'common.product', type: FieldType.reference, required: true, optionsKey: 'list:/products#name'),
      FieldSpec(key: 'unit_id', labelKey: 'settings.units', type: FieldType.reference, required: true, optionsKey: 'lookup:units'),
      FieldSpec(key: 'conversion_factor', labelKey: 'common.quantity', type: FieldType.decimal, required: true),
      FieldSpec(key: 'is_base', labelKey: 'common.active', type: FieldType.boolean),
    ],
  );

  static const ResourceConfig reorderRules = ResourceConfig(
    nameKey: 'dash.low_stock',
    path: '/reorder-rules',
    permissionPrefix: 'inventory.reorder_rule',
    icon: Icons.rule_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('product_id', 'common.product', width: 200, emphasize: true),
      ColumnSpec('warehouse_id', 'common.warehouse', width: 180),
      ColumnSpec('min_quantity', 'common.quantity', type: FieldType.decimal, width: 130, align: MainAxisAlignment.end),
      ColumnSpec('max_quantity', 'common.quantity', type: FieldType.decimal, width: 130, align: MainAxisAlignment.end),
      ColumnSpec('reorder_quantity', 'common.quantity', type: FieldType.decimal, width: 140),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'product_id', labelKey: 'common.product', type: FieldType.reference, required: true, optionsKey: 'list:/products#name'),
      FieldSpec(key: 'warehouse_id', labelKey: 'common.warehouse', type: FieldType.reference, optionsKey: 'list:/warehouses#name'),
      FieldSpec(key: 'min_quantity', labelKey: 'common.quantity', type: FieldType.decimal, required: true),
      FieldSpec(key: 'max_quantity', labelKey: 'common.quantity', type: FieldType.decimal),
      FieldSpec(key: 'reorder_quantity', labelKey: 'common.quantity', type: FieldType.decimal),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig batches = ResourceConfig(
    nameKey: 'nav.inventory',
    path: '/batches',
    permissionPrefix: 'inventory.batch',
    icon: Icons.layers_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('batch_no', 'common.code', width: 150, emphasize: true),
      ColumnSpec('product_id', 'common.product', width: 200),
      ColumnSpec('warehouse_id', 'common.warehouse', width: 160),
      ColumnSpec('manufacturing_date', 'common.from', type: FieldType.date, width: 140),
      ColumnSpec('expiry_date', 'common.due_date', type: FieldType.date, width: 140),
      ColumnSpec('quantity_on_hand', 'common.quantity', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'product_id', labelKey: 'common.product', type: FieldType.reference, required: true, optionsKey: 'list:/products#name'),
      FieldSpec(key: 'batch_no', labelKey: 'common.code', required: true),
      FieldSpec(key: 'warehouse_id', labelKey: 'common.warehouse', type: FieldType.reference, optionsKey: 'list:/warehouses#name'),
      FieldSpec(key: 'manufacturing_date', labelKey: 'common.from', type: FieldType.date),
      FieldSpec(key: 'expiry_date', labelKey: 'common.due_date', type: FieldType.date),
    ],
  );

  static const ResourceConfig serials = ResourceConfig(
    nameKey: 'nav.inventory',
    path: '/serials',
    permissionPrefix: 'inventory.serial',
    icon: Icons.confirmation_number_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('serial_no', 'common.code', width: 170, emphasize: true),
      ColumnSpec('product_id', 'common.product', width: 200),
      ColumnSpec('warehouse_id', 'common.warehouse', width: 160),
      ColumnSpec('status', 'common.status', isStatus: true, width: 120),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'product_id', labelKey: 'common.product', type: FieldType.reference, required: true, optionsKey: 'list:/products#name'),
      FieldSpec(key: 'serial_no', labelKey: 'common.code', required: true),
      FieldSpec(key: 'warehouse_id', labelKey: 'common.warehouse', type: FieldType.reference, optionsKey: 'list:/warehouses#name'),
    ],
  );

  static const ResourceConfig stockBalances = ResourceConfig(
    nameKey: 'dash.inventory',
    path: '/stock/balances',
    permissionPrefix: 'inventory.stock_balance',
    icon: Icons.assessment_outlined,
    readOnly: true,
    canCreate: false,
    canEdit: false,
    canDelete: false,
    breadcrumbs: <String>['nav.inventory', 'dash.inventory'],
    filters: <FilterSpec>[
      FilterSpec(key: 'warehouse_id', labelKey: 'common.warehouse', optionsKey: 'list:/warehouses#name'),
      FilterSpec(
        key: 'low_stock',
        labelKey: 'dash.low_stock',
        options: <DropdownOption>[DropdownOption('true', 'common.yes')],
      ),
    ],
    columns: <ColumnSpec>[
      ColumnSpec('sku', 'common.code', width: 130, emphasize: true),
      ColumnSpec('product_name', 'common.product', width: 240),
      ColumnSpec('warehouse_name', 'common.warehouse', width: 170),
      ColumnSpec('quantity_on_hand', 'common.quantity', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('unit_cost', 'common.price', type: FieldType.decimal, width: 130, align: MainAxisAlignment.end),
      ColumnSpec('stock_value', 'dash.stock_value', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('min_stock', 'dash.low_stock', type: FieldType.decimal, width: 120, align: MainAxisAlignment.end),
    ],
  );

  static const ResourceConfig stockLedger = ResourceConfig(
    nameKey: 'reports.general_ledger',
    path: '/stock/ledger',
    permissionPrefix: 'inventory.stock_ledger',
    icon: Icons.receipt_long_outlined,
    readOnly: true,
    canCreate: false,
    canEdit: false,
    canDelete: false,
    breadcrumbs: <String>['nav.inventory', 'reports.general_ledger'],
    filters: <FilterSpec>[
      FilterSpec(key: 'warehouse_id', labelKey: 'common.warehouse', optionsKey: 'list:/warehouses#name'),
      FilterSpec(key: 'product_id', labelKey: 'common.product', optionsKey: 'list:/products#name'),
    ],
    columns: <ColumnSpec>[
      ColumnSpec('entry_date', 'common.date', type: FieldType.date, width: 120, emphasize: true),
      ColumnSpec('document_no', 'common.document_no', width: 150),
      ColumnSpec('movement_type', 'common.status', width: 150),
      ColumnSpec('quantity_in', 'common.debit', type: FieldType.decimal, width: 120, align: MainAxisAlignment.end),
      ColumnSpec('quantity_out', 'common.credit', type: FieldType.decimal, width: 120, align: MainAxisAlignment.end),
      ColumnSpec('running_balance', 'common.balance', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('unit_cost', 'common.price', type: FieldType.decimal, width: 120, align: MainAxisAlignment.end),
    ],
  );

  // ---------------------------------------------------------------- finance
  static const ResourceConfig accounts = ResourceConfig(
    nameKey: 'nav.accounting',
    path: '/accounts',
    permissionPrefix: 'accounting.account',
    icon: Icons.account_tree_outlined,
    breadcrumbs: <String>['nav.accounting', 'nav.accounting'],
    exportEntity: 'accounts',
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 130, emphasize: true),
      ColumnSpec('name', 'common.name', width: 230),
      ColumnSpec('account_type', 'common.status', width: 140),
      ColumnSpec('normal_balance', 'common.balance', width: 120),
      ColumnSpec('is_group', 'common.status', type: FieldType.boolean, width: 90),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    filters: <FilterSpec>[
      FilterSpec(
        key: 'account_type',
        labelKey: 'common.status',
        options: <DropdownOption>[
          DropdownOption('asset', 'nav.assets'),
          DropdownOption('liability', 'common.balance'),
          DropdownOption('equity', 'common.balance'),
          DropdownOption('revenue', 'nav.sales'),
          DropdownOption('expense', 'nav.expenses'),
        ],
      ),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(
        key: 'account_type',
        labelKey: 'common.status',
        type: FieldType.select,
        options: <DropdownOption>[
          DropdownOption('asset', 'nav.assets'),
          DropdownOption('liability', 'common.balance'),
          DropdownOption('equity', 'common.balance'),
          DropdownOption('revenue', 'nav.sales'),
          DropdownOption('expense', 'nav.expenses'),
        ],
        required: true,
      ),
      FieldSpec(
        key: 'normal_balance',
        labelKey: 'common.balance',
        type: FieldType.select,
        options: <DropdownOption>[DropdownOption('debit', 'common.debit'), DropdownOption('credit', 'common.credit')],
      ),
      FieldSpec(key: 'parent_id', labelKey: 'nav.accounting', type: FieldType.reference, optionsKey: 'list:/accounts#name'),
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'is_group', labelKey: 'common.status', type: FieldType.boolean),
      FieldSpec(key: 'is_postable', labelKey: 'common.status', type: FieldType.boolean, defaultValue: true),
      FieldSpec(key: 'is_cash_account', labelKey: 'nav.treasury', type: FieldType.boolean),
      FieldSpec(key: 'is_bank_account', labelKey: 'nav.treasury', type: FieldType.boolean),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig budgets = ResourceConfig(
    nameKey: 'nav.accounting',
    path: '/budgets',
    permissionPrefix: 'expenses.budget',
    icon: Icons.savings_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 120, emphasize: true),
      ColumnSpec('name', 'common.name', width: 220),
      ColumnSpec('total_amount', 'common.total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('actual_amount', 'common.amount', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('committed_amount', 'common.amount', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'fiscal_year_id', labelKey: 'common.period', required: true),
      FieldSpec(key: 'total_amount', labelKey: 'common.total', type: FieldType.decimal, required: true),
      FieldSpec(
        key: 'scope_type',
        labelKey: 'common.status',
        type: FieldType.select,
        options: <DropdownOption>[
          DropdownOption('company', 'common.company'),
          DropdownOption('branch', 'common.branch'),
          DropdownOption('cost_center', 'common.cost_center'),
          DropdownOption('department', 'common.department'),
        ],
        defaultValue: 'company',
      ),
      FieldSpec(key: 'start_date', labelKey: 'common.from', type: FieldType.date),
      FieldSpec(key: 'end_date', labelKey: 'common.to', type: FieldType.date),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
  );

  static const ResourceConfig postingRules = ResourceConfig(
    nameKey: 'nav.accounting',
    path: '/posting-rules',
    permissionPrefix: 'accounting.posting_rule',
    icon: Icons.rule_folder_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('document_type', 'common.document_no', width: 170, emphasize: true),
      ColumnSpec('event', 'common.status', width: 130),
      ColumnSpec('line_role', 'common.details', width: 150),
      ColumnSpec('entry_side', 'common.debit', width: 100),
      ColumnSpec('amount_source', 'common.amount', width: 150),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'document_type', labelKey: 'common.document_no', required: true),
      FieldSpec(key: 'event', labelKey: 'common.status', defaultValue: 'post'),
      FieldSpec(key: 'line_role', labelKey: 'common.details', required: true),
      FieldSpec(key: 'entry_side', labelKey: 'common.debit', type: FieldType.select, options: <DropdownOption>[
        DropdownOption('debit', 'common.debit'),
        DropdownOption('credit', 'common.credit'),
      ]),
      FieldSpec(key: 'account_source', labelKey: 'nav.accounting'),
      FieldSpec(key: 'sequence_no', labelKey: 'common.page', type: FieldType.integer, defaultValue: 10),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig cashAccounts = ResourceConfig(
    nameKey: 'nav.treasury',
    path: '/cash-accounts',
    permissionPrefix: 'treasury.cash_account',
    icon: Icons.account_balance_wallet_outlined,
    breadcrumbs: <String>['nav.treasury', 'nav.treasury'],
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 120, emphasize: true),
      ColumnSpec('name', 'common.name', width: 200),
      ColumnSpec('currency_code', 'common.currency', width: 110),
      ColumnSpec('opening_balance', 'common.balance', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('current_balance', 'common.balance', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'branch_id', labelKey: 'common.branch', type: FieldType.reference, optionsKey: 'lookup:branches'),
      FieldSpec(key: 'custodian_id', labelKey: 'common.employee', type: FieldType.reference, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'opening_balance', labelKey: 'common.balance', type: FieldType.decimal),
      FieldSpec(key: 'cash_limit', labelKey: 'common.total', type: FieldType.decimal),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig bankAccounts = ResourceConfig(
    nameKey: 'nav.treasury',
    path: '/bank-accounts',
    permissionPrefix: 'treasury.bank_account',
    icon: Icons.account_balance_outlined,
    breadcrumbs: <String>['nav.treasury', 'nav.treasury'],
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 110, emphasize: true),
      ColumnSpec('name', 'common.name', width: 200),
      ColumnSpec('bank_name', 'common.details', width: 180),
      ColumnSpec('account_number', 'common.reference', width: 160),
      ColumnSpec('currency_code', 'common.currency', width: 110),
      ColumnSpec('current_balance', 'common.balance', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'bank_name', labelKey: 'common.details', required: true),
      FieldSpec(key: 'branch_name', labelKey: 'common.branch'),
      FieldSpec(key: 'account_number', labelKey: 'common.reference'),
      FieldSpec(key: 'iban', labelKey: 'common.reference'),
      FieldSpec(key: 'swift_code', labelKey: 'common.reference'),
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'opening_balance', labelKey: 'common.balance', type: FieldType.decimal),
      FieldSpec(key: 'overdraft_limit', labelKey: 'common.total', type: FieldType.decimal),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig cheques = ResourceConfig(
    nameKey: 'nav.treasury',
    path: '/cheques',
    permissionPrefix: 'treasury.cheque',
    icon: Icons.receipt_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('cheque_number', 'common.code', width: 150, emphasize: true),
      ColumnSpec('direction', 'common.status', width: 110),
      ColumnSpec('party_type', 'common.party', width: 110),
      ColumnSpec('amount', 'common.amount', type: FieldType.decimal, width: 130, align: MainAxisAlignment.end),
      ColumnSpec('due_date', 'common.due_date', type: FieldType.date, width: 130),
      ColumnSpec('status', 'common.status', isStatus: true, width: 120),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'cheque_number', labelKey: 'common.code', required: true),
      FieldSpec(key: 'direction', labelKey: 'common.status', type: FieldType.select, options: <DropdownOption>[
        DropdownOption('incoming', 'common.debit'),
        DropdownOption('outgoing', 'common.credit'),
      ], required: true),
      FieldSpec(key: 'party_type', labelKey: 'common.party', type: FieldType.select, options: <DropdownOption>[
        DropdownOption('customer', 'common.customer'),
        DropdownOption('supplier', 'common.supplier'),
      ]),
      FieldSpec(key: 'party_id', labelKey: 'common.party'),
      FieldSpec(key: 'amount', labelKey: 'common.amount', type: FieldType.decimal, required: true),
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'bank_name', labelKey: 'common.details'),
      FieldSpec(key: 'issue_date', labelKey: 'common.date', type: FieldType.date),
      FieldSpec(key: 'due_date', labelKey: 'common.due_date', type: FieldType.date),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
  );

  // ------------------------------------------------- expenses and assets
  static const ResourceConfig expenseCategories = ResourceConfig(
    nameKey: 'nav.expenses',
    path: '/expense-categories',
    permissionPrefix: 'expenses.expense_category',
    icon: Icons.category_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 120, emphasize: true),
      ColumnSpec('name', 'common.name', width: 230),
      ColumnSpec('name_ar', 'common.name_ar', width: 200),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'account_id', labelKey: 'nav.accounting', type: FieldType.reference, optionsKey: 'list:/accounts#name'),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig assetCategories = ResourceConfig(
    nameKey: 'nav.assets',
    path: '/asset-categories',
    permissionPrefix: 'assets.asset_category',
    icon: Icons.category_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 120, emphasize: true),
      ColumnSpec('name', 'common.name', width: 220),
      ColumnSpec('depreciation_method', 'common.status', width: 170),
      ColumnSpec('useful_life_years', 'common.quantity', type: FieldType.decimal, width: 140),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(
        key: 'depreciation_method',
        labelKey: 'common.status',
        type: FieldType.select,
        options: <DropdownOption>[
          DropdownOption('straight_line', 'common.total'),
          DropdownOption('declining_balance', 'common.balance'),
          DropdownOption('units_of_production', 'common.quantity'),
        ],
        defaultValue: 'straight_line',
      ),
      FieldSpec(key: 'useful_life_years', labelKey: 'common.quantity', type: FieldType.decimal, defaultValue: 5),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig assets = ResourceConfig(
    nameKey: 'nav.assets',
    path: '/assets',
    permissionPrefix: 'assets.asset',
    icon: Icons.precision_manufacturing_outlined,
    breadcrumbs: <String>['nav.assets', 'nav.assets'],
    exportEntity: 'assets',
    columns: <ColumnSpec>[
      ColumnSpec('asset_code', 'common.code', width: 130, emphasize: true),
      ColumnSpec('name', 'common.name', width: 210),
      ColumnSpec('category_id', 'nav.assets', width: 150),
      ColumnSpec('acquisition_cost', 'common.amount', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('accumulated_depreciation', 'common.total', type: FieldType.decimal, width: 170, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 120),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'asset_code', labelKey: 'common.code'),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'category_id', labelKey: 'nav.assets', type: FieldType.reference, required: true, optionsKey: 'list:/asset-categories#name'),
      FieldSpec(key: 'branch_id', labelKey: 'common.branch', type: FieldType.reference, optionsKey: 'lookup:branches'),
      FieldSpec(key: 'location', labelKey: 'common.details'),
      FieldSpec(key: 'acquisition_cost', labelKey: 'common.amount', type: FieldType.decimal, required: true),
      FieldSpec(key: 'acquisition_date', labelKey: 'common.date', type: FieldType.date),
      FieldSpec(key: 'useful_life_years', labelKey: 'common.quantity', type: FieldType.decimal),
      FieldSpec(key: 'salvage_value', labelKey: 'common.total', type: FieldType.decimal),
      FieldSpec(key: 'custodian_id', labelKey: 'common.employee', type: FieldType.reference, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
  );

  static const ResourceConfig assetMaintenance = ResourceConfig(
    nameKey: 'nav.assets',
    path: '/asset-maintenance',
    permissionPrefix: 'assets.asset_maintenance',
    icon: Icons.build_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('asset_id', 'nav.assets', width: 200, emphasize: true),
      ColumnSpec('maintenance_type', 'common.status', width: 150),
      ColumnSpec('scheduled_date', 'common.date', type: FieldType.date, width: 130),
      ColumnSpec('cost', 'common.amount', type: FieldType.decimal, width: 130, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'asset_id', labelKey: 'nav.assets', type: FieldType.reference, required: true, optionsKey: 'list:/assets#name'),
      FieldSpec(key: 'maintenance_type', labelKey: 'common.status', type: FieldType.select, options: <DropdownOption>[
        DropdownOption('preventive', 'common.status'),
        DropdownOption('corrective', 'common.status'),
      ]),
      FieldSpec(key: 'scheduled_date', labelKey: 'common.date', type: FieldType.date, required: true),
      FieldSpec(key: 'performed_date', labelKey: 'common.date', type: FieldType.date),
      FieldSpec(key: 'cost', labelKey: 'common.amount', type: FieldType.decimal),
      FieldSpec(key: 'vendor_id', labelKey: 'common.supplier', type: FieldType.reference, optionsKey: 'list:/suppliers#name'),
      FieldSpec(key: 'description', labelKey: 'common.description', type: FieldType.multiline, span: 2),
    ],
  );

  // ------------------------------------------------------ people/projects
  static const ResourceConfig employees = ResourceConfig(
    nameKey: 'common.employee',
    path: '/employees',
    permissionPrefix: 'hr.employee',
    icon: Icons.badge_outlined,
    breadcrumbs: <String>['nav.hr', 'common.employee'],
    exportEntity: 'employees',
    columns: <ColumnSpec>[
      ColumnSpec('employee_no', 'common.code', width: 130, emphasize: true),
      ColumnSpec('full_name', 'common.name', width: 220),
      ColumnSpec('job_title', 'common.details', width: 170),
      ColumnSpec('department_id', 'common.department', width: 150),
      ColumnSpec('hire_date', 'common.date', type: FieldType.date, width: 130),
      ColumnSpec('basic_salary', 'common.amount', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'employee_no', labelKey: 'common.code'),
      FieldSpec(key: 'full_name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'full_name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'job_title', labelKey: 'common.details'),
      FieldSpec(key: 'position_id', labelKey: 'nav.hr', type: FieldType.reference, optionsKey: 'list:/positions#name'),
      FieldSpec(key: 'department_id', labelKey: 'common.department', type: FieldType.reference, optionsKey: 'lookup:departments'),
      FieldSpec(key: 'branch_id', labelKey: 'common.branch', type: FieldType.reference, optionsKey: 'lookup:branches'),
      FieldSpec(key: 'manager_id', labelKey: 'common.employee', type: FieldType.reference, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'email', labelKey: 'login.email'),
      FieldSpec(key: 'phone', labelKey: 'common.reference'),
      FieldSpec(key: 'national_id', labelKey: 'common.code'),
      FieldSpec(key: 'hire_date', labelKey: 'common.date', type: FieldType.date),
      FieldSpec(key: 'basic_salary', labelKey: 'common.amount', type: FieldType.decimal),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig positions = ResourceConfig(
    nameKey: 'nav.hr',
    path: '/positions',
    permissionPrefix: 'hr.position',
    icon: Icons.work_outline,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 120, emphasize: true),
      ColumnSpec('name', 'common.name', width: 220),
      ColumnSpec('department_id', 'common.department', width: 170),
      ColumnSpec('grade', 'common.status', width: 110),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'department_id', labelKey: 'common.department', type: FieldType.reference, optionsKey: 'lookup:departments'),
      FieldSpec(key: 'grade', labelKey: 'common.status'),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig employeeContracts = ResourceConfig(
    nameKey: 'nav.hr',
    path: '/employee-contracts',
    permissionPrefix: 'hr.employee_contract',
    icon: Icons.description_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('contract_no', 'common.code', width: 140, emphasize: true),
      ColumnSpec('employee_id', 'common.employee', width: 200),
      ColumnSpec('start_date', 'common.from', type: FieldType.date, width: 130),
      ColumnSpec('end_date', 'common.to', type: FieldType.date, width: 130),
      ColumnSpec('basic_salary', 'common.amount', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'employee_id', labelKey: 'common.employee', type: FieldType.reference, required: true, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'start_date', labelKey: 'common.from', type: FieldType.date, required: true),
      FieldSpec(key: 'end_date', labelKey: 'common.to', type: FieldType.date),
      FieldSpec(key: 'basic_salary', labelKey: 'common.amount', type: FieldType.decimal, required: true),
      FieldSpec(key: 'housing_allowance', labelKey: 'common.amount', type: FieldType.decimal),
      FieldSpec(key: 'transport_allowance', labelKey: 'common.amount', type: FieldType.decimal),
      FieldSpec(key: 'contract_type', labelKey: 'common.status'),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
  );

  static const ResourceConfig attendanceRecords = ResourceConfig(
    nameKey: 'nav.hr',
    path: '/attendance-records',
    permissionPrefix: 'hr.attendance',
    icon: Icons.fingerprint,
    columns: <ColumnSpec>[
      ColumnSpec('employee_id', 'common.employee', width: 200, emphasize: true),
      ColumnSpec('attendance_date', 'common.date', type: FieldType.date, width: 130),
      ColumnSpec('check_in', 'common.from', type: FieldType.dateTime, width: 150),
      ColumnSpec('check_out', 'common.to', type: FieldType.dateTime, width: 150),
      ColumnSpec('worked_hours', 'common.quantity', type: FieldType.decimal, width: 120, align: MainAxisAlignment.end),
      ColumnSpec('overtime_hours', 'common.quantity', type: FieldType.decimal, width: 130, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    filters: <FilterSpec>[
      FilterSpec(key: 'date_from', labelKey: 'common.from', type: FieldType.date, queryParam: 'date_from'),
      FilterSpec(key: 'date_to', labelKey: 'common.to', type: FieldType.date, queryParam: 'date_to'),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'employee_id', labelKey: 'common.employee', type: FieldType.reference, required: true, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'attendance_date', labelKey: 'common.date', type: FieldType.date, required: true),
      FieldSpec(key: 'check_in', labelKey: 'common.from', type: FieldType.dateTime),
      FieldSpec(key: 'check_out', labelKey: 'common.to', type: FieldType.dateTime),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
  );

  static const ResourceConfig shifts = ResourceConfig(
    nameKey: 'nav.hr',
    path: '/shifts',
    permissionPrefix: 'hr.shift',
    icon: Icons.schedule_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 120, emphasize: true),
      ColumnSpec('name', 'common.name', width: 200),
      ColumnSpec('start_time', 'common.from', width: 130),
      ColumnSpec('end_time', 'common.to', width: 130),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'start_time', labelKey: 'common.from', required: true),
      FieldSpec(key: 'end_time', labelKey: 'common.to', required: true),
      FieldSpec(key: 'break_minutes', labelKey: 'common.quantity', type: FieldType.integer),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig shiftAssignments = ResourceConfig(
    nameKey: 'nav.hr',
    path: '/shift-assignments',
    permissionPrefix: 'hr.shift',
    icon: Icons.event_available_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('employee_id', 'common.employee', width: 200, emphasize: true),
      ColumnSpec('shift_id', 'pos.shift', width: 180),
      ColumnSpec('from_date', 'common.from', type: FieldType.date, width: 130),
      ColumnSpec('to_date', 'common.to', type: FieldType.date, width: 130),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'employee_id', labelKey: 'common.employee', type: FieldType.reference, required: true, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'shift_id', labelKey: 'pos.shift', type: FieldType.reference, required: true, optionsKey: 'list:/shifts#name'),
      FieldSpec(key: 'from_date', labelKey: 'common.from', type: FieldType.date, required: true),
      FieldSpec(key: 'to_date', labelKey: 'common.to', type: FieldType.date),
    ],
  );

  static const ResourceConfig holidays = ResourceConfig(
    nameKey: 'nav.hr',
    path: '/holidays',
    permissionPrefix: 'hr.holiday',
    icon: Icons.beach_access_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('name', 'common.name', width: 220, emphasize: true),
      ColumnSpec('holiday_date', 'common.date', type: FieldType.date, width: 140),
      ColumnSpec('is_paid', 'status.paid', type: FieldType.boolean, width: 100),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'holiday_date', labelKey: 'common.date', type: FieldType.date, required: true),
      FieldSpec(key: 'is_paid', labelKey: 'status.paid', type: FieldType.boolean, defaultValue: true),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
  );

  static const ResourceConfig leaveTypes = ResourceConfig(
    nameKey: 'nav.hr',
    path: '/leave-type-master',
    permissionPrefix: 'hr.leave_type',
    icon: Icons.event_busy_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 120, emphasize: true),
      ColumnSpec('name', 'common.name', width: 220),
      ColumnSpec('annual_quota', 'common.quantity', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('is_paid', 'status.paid', type: FieldType.boolean, width: 100),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'annual_quota', labelKey: 'common.quantity', type: FieldType.decimal),
      FieldSpec(key: 'is_paid', labelKey: 'status.paid', type: FieldType.boolean, defaultValue: true),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig leaveBalances = ResourceConfig(
    nameKey: 'nav.hr',
    path: '/leave-balances',
    permissionPrefix: 'hr.leave_balance',
    icon: Icons.calendar_view_month_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('employee_id', 'common.employee', width: 200, emphasize: true),
      ColumnSpec('leave_type_id', 'nav.hr', width: 200),
      ColumnSpec('year', 'common.period', type: FieldType.integer, width: 100),
      ColumnSpec('entitled_days', 'common.quantity', type: FieldType.decimal, width: 130, align: MainAxisAlignment.end),
      ColumnSpec('used_days', 'common.quantity', type: FieldType.decimal, width: 130, align: MainAxisAlignment.end),
      ColumnSpec('remaining_days', 'common.balance', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'employee_id', labelKey: 'common.employee', type: FieldType.reference, required: true, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'leave_type_id', labelKey: 'nav.hr', type: FieldType.reference, required: true, optionsKey: 'list:/leave-type-master#name'),
      FieldSpec(key: 'year', labelKey: 'common.period', type: FieldType.integer, required: true),
      FieldSpec(key: 'entitled_days', labelKey: 'common.quantity', type: FieldType.decimal),
      FieldSpec(key: 'used_days', labelKey: 'common.quantity', type: FieldType.decimal),
    ],
  );

  static const ResourceConfig loans = ResourceConfig(
    nameKey: 'nav.hr',
    path: '/loans',
    permissionPrefix: 'hr.loan',
    icon: Icons.request_quote_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('loan_no', 'common.code', width: 130, emphasize: true),
      ColumnSpec('employee_id', 'common.employee', width: 200),
      ColumnSpec('amount', 'common.amount', type: FieldType.decimal, width: 130, align: MainAxisAlignment.end),
      ColumnSpec('installment_amount', 'common.amount', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('remaining_amount', 'common.balance', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'employee_id', labelKey: 'common.employee', type: FieldType.reference, required: true, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'amount', labelKey: 'common.amount', type: FieldType.decimal, required: true),
      FieldSpec(key: 'installments', labelKey: 'common.quantity', type: FieldType.integer, defaultValue: 6),
      FieldSpec(key: 'installment_amount', labelKey: 'common.amount', type: FieldType.decimal),
      FieldSpec(key: 'start_date', labelKey: 'common.from', type: FieldType.date),
      FieldSpec(key: 'reason', labelKey: 'common.reason', type: FieldType.multiline, span: 2),
    ],
  );

  static const ResourceConfig projects = ResourceConfig(
    nameKey: 'nav.project',
    path: '/projects',
    permissionPrefix: 'projects.project',
    icon: Icons.workspaces_outline,
    breadcrumbs: <String>['nav.project', 'nav.project'],
    exportEntity: 'projects',
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 120, emphasize: true),
      ColumnSpec('name', 'common.name', width: 220),
      ColumnSpec('customer_id', 'common.customer', width: 180),
      ColumnSpec('start_date', 'common.from', type: FieldType.date, width: 130),
      ColumnSpec('end_date', 'common.to', type: FieldType.date, width: 130),
      ColumnSpec('budget_amount', 'common.total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 120),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'customer_id', labelKey: 'common.customer', type: FieldType.reference, optionsKey: 'list:/customers#name'),
      FieldSpec(key: 'project_manager_id', labelKey: 'common.employee', type: FieldType.reference, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'start_date', labelKey: 'common.from', type: FieldType.date),
      FieldSpec(key: 'end_date', labelKey: 'common.to', type: FieldType.date),
      FieldSpec(key: 'budget_amount', labelKey: 'common.total', type: FieldType.decimal),
      FieldSpec(key: 'status', labelKey: 'common.status', type: FieldType.select, options: <DropdownOption>[
        DropdownOption('planned', 'status.draft'),
        DropdownOption('in_progress', 'status.in_progress'),
        DropdownOption('on_hold', 'status.pending'),
        DropdownOption('completed', 'status.completed'),
      ]),
      FieldSpec(key: 'description', labelKey: 'common.description', type: FieldType.multiline, span: 2),
    ],
  );

  static const ResourceConfig projectPhases = ResourceConfig(
    nameKey: 'nav.project',
    path: '/project-phases',
    permissionPrefix: 'projects.project_phase',
    icon: Icons.timeline_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('name', 'common.name', width: 200, emphasize: true),
      ColumnSpec('project_id', 'nav.project', width: 200),
      ColumnSpec('start_date', 'common.from', type: FieldType.date, width: 130),
      ColumnSpec('end_date', 'common.to', type: FieldType.date, width: 130),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'project_id', labelKey: 'nav.project', type: FieldType.reference, required: true, optionsKey: 'list:/projects#name'),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'start_date', labelKey: 'common.from', type: FieldType.date),
      FieldSpec(key: 'end_date', labelKey: 'common.to', type: FieldType.date),
      FieldSpec(key: 'budget_amount', labelKey: 'common.total', type: FieldType.decimal),
    ],
  );

  static const ResourceConfig projectTasks = ResourceConfig(
    nameKey: 'nav.project',
    path: '/project-tasks',
    permissionPrefix: 'projects.task',
    icon: Icons.checklist_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('name', 'common.name', width: 230, emphasize: true),
      ColumnSpec('project_id', 'nav.project', width: 180),
      ColumnSpec('phase_id', 'workflow.step', width: 150),
      ColumnSpec('assignee_id', 'common.employee', width: 160),
      ColumnSpec('due_date', 'common.due_date', type: FieldType.date, width: 130),
      ColumnSpec('progress_percent', 'common.total', type: FieldType.decimal, width: 120, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'project_id', labelKey: 'nav.project', type: FieldType.reference, required: true, optionsKey: 'list:/projects#name'),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'phase_id', labelKey: 'workflow.step', type: FieldType.reference, optionsKey: 'list:/project-phases#name'),
      FieldSpec(key: 'assignee_id', labelKey: 'common.employee', type: FieldType.reference, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'start_date', labelKey: 'common.from', type: FieldType.date),
      FieldSpec(key: 'due_date', labelKey: 'common.due_date', type: FieldType.date),
      FieldSpec(key: 'estimated_hours', labelKey: 'common.quantity', type: FieldType.decimal),
      FieldSpec(key: 'progress_percent', labelKey: 'common.total', type: FieldType.decimal),
      FieldSpec(key: 'description', labelKey: 'common.description', type: FieldType.multiline, span: 2),
    ],
  );

  static const ResourceConfig projectResources = ResourceConfig(
    nameKey: 'nav.project',
    path: '/project-resources',
    permissionPrefix: 'projects.project_resource',
    icon: Icons.groups_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('project_id', 'nav.project', width: 200, emphasize: true),
      ColumnSpec('employee_id', 'common.employee', width: 200),
      ColumnSpec('role', 'common.status', width: 150),
      ColumnSpec('allocation_percent', 'common.total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('hourly_rate', 'common.price', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'project_id', labelKey: 'nav.project', type: FieldType.reference, required: true, optionsKey: 'list:/projects#name'),
      FieldSpec(key: 'employee_id', labelKey: 'common.employee', type: FieldType.reference, required: true, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'role', labelKey: 'common.status'),
      FieldSpec(key: 'allocation_percent', labelKey: 'common.total', type: FieldType.decimal),
      FieldSpec(key: 'hourly_rate', labelKey: 'common.price', type: FieldType.decimal),
      FieldSpec(key: 'from_date', labelKey: 'common.from', type: FieldType.date),
      FieldSpec(key: 'to_date', labelKey: 'common.to', type: FieldType.date),
    ],
  );

  // -------------------------------------------------------- manufacturing
  static const ResourceConfig boms = ResourceConfig(
    nameKey: 'nav.manufacturing',
    path: '/boms',
    permissionPrefix: 'manufacturing.bom',
    icon: Icons.account_tree_outlined,
    breadcrumbs: <String>['nav.manufacturing', 'nav.manufacturing'],
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 130, emphasize: true),
      ColumnSpec('product_id', 'common.product', width: 210),
      ColumnSpec('version', 'common.status', width: 110),
      ColumnSpec('quantity', 'common.quantity', type: FieldType.decimal, width: 120, align: MainAxisAlignment.end),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'product_id', labelKey: 'common.product', type: FieldType.reference, required: true, optionsKey: 'list:/products#name'),
      FieldSpec(key: 'version', labelKey: 'common.status', defaultValue: '1.0'),
      FieldSpec(key: 'quantity', labelKey: 'common.quantity', type: FieldType.decimal, defaultValue: 1),
      FieldSpec(key: 'unit_id', labelKey: 'settings.units', type: FieldType.reference, optionsKey: 'lookup:units'),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
  );

  static const ResourceConfig routings = ResourceConfig(
    nameKey: 'nav.manufacturing',
    path: '/routings',
    permissionPrefix: 'manufacturing.routing',
    icon: Icons.route_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 130, emphasize: true),
      ColumnSpec('product_id', 'common.product', width: 210),
      ColumnSpec('name', 'common.name', width: 200),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'product_id', labelKey: 'common.product', type: FieldType.reference, required: true, optionsKey: 'list:/products#name'),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig workCenters = ResourceConfig(
    nameKey: 'nav.manufacturing',
    path: '/work-center-master',
    permissionPrefix: 'manufacturing.work_center',
    icon: Icons.factory_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 130, emphasize: true),
      ColumnSpec('name', 'common.name', width: 220),
      ColumnSpec('capacity_per_hour', 'common.quantity', type: FieldType.decimal, width: 160, align: MainAxisAlignment.end),
      ColumnSpec('hourly_rate', 'common.price', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'branch_id', labelKey: 'common.branch', type: FieldType.reference, optionsKey: 'lookup:branches'),
      FieldSpec(key: 'capacity_per_hour', labelKey: 'common.quantity', type: FieldType.decimal),
      FieldSpec(key: 'hourly_rate', labelKey: 'common.price', type: FieldType.decimal),
      FieldSpec(key: 'cost_center_id', labelKey: 'common.cost_center', type: FieldType.reference, optionsKey: 'lookup:cost-centers'),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  // --------------------------------------------------------------- service
  static const ResourceConfig contractsMasterExtra = ResourceConfig(
    nameKey: 'nav.service',
    path: '/warranties',
    permissionPrefix: 'service.warranty',
    icon: Icons.verified_user_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 130, emphasize: true),
      ColumnSpec('customer_id', 'common.customer', width: 200),
      ColumnSpec('product_id', 'common.product', width: 190),
      ColumnSpec('start_date', 'common.from', type: FieldType.date, width: 130),
      ColumnSpec('end_date', 'common.to', type: FieldType.date, width: 130),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code'),
      FieldSpec(key: 'customer_id', labelKey: 'common.customer', type: FieldType.reference, optionsKey: 'list:/customers#name'),
      FieldSpec(key: 'product_id', labelKey: 'common.product', type: FieldType.reference, optionsKey: 'list:/products#name'),
      FieldSpec(key: 'start_date', labelKey: 'common.from', type: FieldType.date, required: true),
      FieldSpec(key: 'end_date', labelKey: 'common.to', type: FieldType.date, required: true),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
  );

  static const ResourceConfig warranties = ResourceConfig(
    nameKey: 'nav.service',
    path: '/warranties',
    permissionPrefix: 'service.warranty',
    icon: Icons.verified_user_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 130, emphasize: true),
      ColumnSpec('customer_id', 'common.customer', width: 200),
      ColumnSpec('product_id', 'common.product', width: 190),
      ColumnSpec('start_date', 'common.from', type: FieldType.date, width: 130),
      ColumnSpec('end_date', 'common.to', type: FieldType.date, width: 130),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'customer_id', labelKey: 'common.customer', type: FieldType.reference, optionsKey: 'list:/customers#name'),
      FieldSpec(key: 'product_id', labelKey: 'common.product', type: FieldType.reference, optionsKey: 'list:/products#name'),
      FieldSpec(key: 'start_date', labelKey: 'common.from', type: FieldType.date, required: true),
      FieldSpec(key: 'end_date', labelKey: 'common.to', type: FieldType.date, required: true),
    ],
  );

  static const ResourceConfig technicianSchedules = ResourceConfig(
    nameKey: 'nav.service',
    path: '/schedules',
    permissionPrefix: 'service.technician_schedule',
    icon: Icons.calendar_today_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('technician_id', 'common.employee', width: 200, emphasize: true),
      ColumnSpec('scheduled_date', 'common.date', type: FieldType.date, width: 140),
      ColumnSpec('start_time', 'common.from', width: 120),
      ColumnSpec('end_time', 'common.to', width: 120),
      ColumnSpec('work_order_id', 'nav.service', width: 190),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'technician_id', labelKey: 'common.employee', type: FieldType.reference, required: true, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'scheduled_date', labelKey: 'common.date', type: FieldType.date, required: true),
      FieldSpec(key: 'start_time', labelKey: 'common.from'),
      FieldSpec(key: 'end_time', labelKey: 'common.to'),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
  );

  static const ResourceConfig posTerminals = ResourceConfig(
    nameKey: 'pos.terminal',
    path: '/pos/terminals',
    permissionPrefix: 'sales.pos_terminal',
    icon: Icons.point_of_sale,
    breadcrumbs: <String>['nav.pos', 'pos.terminal'],
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 130, emphasize: true),
      ColumnSpec('name', 'common.name', width: 200),
      ColumnSpec('warehouse_id', 'common.warehouse', width: 170),
      ColumnSpec('allow_negative_stock', 'status.pending', type: FieldType.boolean, width: 150),
      ColumnSpec('allow_discount', 'common.discount', type: FieldType.boolean, width: 130),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'branch_id', labelKey: 'common.branch', type: FieldType.reference, optionsKey: 'lookup:branches'),
      FieldSpec(key: 'warehouse_id', labelKey: 'common.warehouse', type: FieldType.reference, required: true, optionsKey: 'list:/warehouses#name'),
      FieldSpec(key: 'cash_account_id', labelKey: 'nav.treasury', type: FieldType.reference, optionsKey: 'list:/cash-accounts#name'),
      FieldSpec(key: 'default_customer_id', labelKey: 'common.customer', type: FieldType.reference, optionsKey: 'list:/customers#name'),
      FieldSpec(key: 'allow_discount', labelKey: 'common.discount', type: FieldType.boolean, defaultValue: true),
      FieldSpec(key: 'max_discount_percent', labelKey: 'common.discount', type: FieldType.decimal),
      FieldSpec(key: 'allow_negative_stock', labelKey: 'status.pending', type: FieldType.boolean),
      FieldSpec(key: 'receipt_footer', labelKey: 'pos.receipt', span: 2),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig commissions = ResourceConfig(
    nameKey: 'nav.sales',
    path: '/commissions',
    permissionPrefix: 'sales.sales_commission',
    icon: Icons.percent,
    columns: <ColumnSpec>[
      ColumnSpec('salesperson_id', 'common.created_by', width: 200, emphasize: true),
      ColumnSpec('invoice_id', 'nav.sales', width: 190),
      ColumnSpec('base_amount', 'common.amount', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('commission_percent', 'common.total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('commission_amount', 'common.total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    readOnly: true,
    canCreate: false,
    canEdit: false,
    canDelete: false,
    fields: <FieldSpec>[],
  );
}
