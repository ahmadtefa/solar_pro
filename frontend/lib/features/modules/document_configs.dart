import 'package:flutter/material.dart';

import '../../shared/resource/document_config.dart';
import '../../shared/resource/resource_config.dart';

/// Lifecycle screens for every document type in the ERP.
///
/// Each entry mirrors one backend document router: the same six lifecycle
/// actions (submit/approve/reject/post/unpost/cancel) plus the module specific
/// conversions (order -> delivery -> invoice, request -> RFQ -> order...).
class DocumentConfigs {
  const DocumentConfigs._();

  /// Product picker used by every line grid.
  static const FieldSpec productLine = FieldSpec(
    key: 'product_id',
    labelKey: 'common.product',
    type: FieldType.reference,
    required: true,
    optionsKey: 'list:/products#name',
    span: 2,
  );
  static const FieldSpec quantityLine = FieldSpec(
    key: 'quantity',
    labelKey: 'common.quantity',
    type: FieldType.decimal,
    required: true,
    defaultValue: 1,
  );
  static const FieldSpec priceLine = FieldSpec(
    key: 'unit_price',
    labelKey: 'common.unit_price',
    type: FieldType.decimal,
    required: true,
  );
  static const FieldSpec discountLine = FieldSpec(key: 'discount_percent', labelKey: 'common.discount', type: FieldType.decimal);
  static const FieldSpec taxLine = FieldSpec(
    key: 'tax_id',
    labelKey: 'common.tax',
    type: FieldType.reference,
    optionsKey: 'lookup:taxes',
  );
  static const FieldSpec warehouseLine = FieldSpec(
    key: 'warehouse_id',
    labelKey: 'common.warehouse',
    type: FieldType.reference,
    optionsKey: 'list:/warehouses#name',
  );
  static const FieldSpec descriptionLine = FieldSpec(
    key: 'description',
    labelKey: 'common.description',
    type: FieldType.text,
    span: 2,
  );

  static Map<String, DocumentConfig> all() => <String, DocumentConfig>{
        'quotations': quotations,
        'sales-orders': salesOrders,
        'deliveries': deliveries,
        'sales-invoices': salesInvoices,
        'credit-notes': creditNotes,
        'purchase-requests': purchaseRequests,
        'rfqs': rfqs,
        'supplier-quotations': supplierQuotations,
        'purchase-orders': purchaseOrders,
        'goods-receipts': goodsReceipts,
        'purchase-invoices': purchaseInvoices,
        'debit-notes': debitNotes,
        'stock-adjustments': stockAdjustments,
        'stock-transfers': stockTransfers,
        'stock-counts': stockCounts,
        'journal-entries': journalEntries,
        'payments': payments,
        'treasury-transfers': treasuryTransfers,
        'expenses': expenses,
        'expense-claims': expenseClaims,
        'advances': advances,
        'asset-transfers': assetTransfers,
        'asset-disposals': assetDisposals,
        'leave-requests': leaveRequests,
        'timesheets': timesheets,
        'production-orders': productionOrders,
        'work-orders': workOrders,
        'service-contracts': serviceContracts,
      };

  // ------------------------------------------------------------------ sales
  static const DocumentConfig quotations = DocumentConfig(
    nameKey: 'nav.sales',
    singularKey: 'nav.sales',
    path: '/quotations',
    permissionPrefix: 'sales.quotation',
    icon: Icons.request_quote_outlined,
    breadcrumbs: <String>['nav.sales', 'nav.sales'],
    statuses: <String>['draft', 'submitted', 'approved', 'rejected', 'posted', 'cancelled'],
    linesPath: 'lines',
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('customer_id', 'common.customer', width: 200),
      ColumnSpec('valid_until', 'common.due_date', type: FieldType.date, width: 130),
      ColumnSpec('total_amount', 'common.grand_total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'customer_id', labelKey: 'common.customer', type: FieldType.reference, required: true, optionsKey: 'list:/customers#name', span: 2),
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'valid_until', labelKey: 'common.due_date', type: FieldType.date),
      FieldSpec(key: 'warehouse_id', labelKey: 'common.warehouse', type: FieldType.reference, optionsKey: 'list:/warehouses#name'),
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'reference', labelKey: 'common.reference'),
      FieldSpec(key: 'discount_percent', labelKey: 'common.discount', type: FieldType.decimal),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[productLine, descriptionLine, quantityLine, priceLine, discountLine, taxLine, warehouseLine],
    extraActions: <DocumentActionSpec>[
      DocumentActionSpec(
        endpoint: 'convert-to-order',
        labelKey: 'action.convert',
        permissionAction: 'create',
        icon: Icons.swap_horiz,
        confirmKey: 'common.confirm',
        visibleWhen: <String>['approved', 'posted'],
      ),
    ],
  );

  static const DocumentConfig salesOrders = DocumentConfig(
    nameKey: 'nav.sales',
    singularKey: 'nav.sales',
    path: '/sales-orders',
    permissionPrefix: 'sales.sales_order',
    icon: Icons.shopping_cart_outlined,
    breadcrumbs: <String>['nav.sales', 'nav.sales'],
    statuses: <String>['draft', 'submitted', 'approved', 'rejected', 'posted', 'partially_fulfilled', 'fulfilled', 'cancelled'],
    linesPath: 'lines',
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('customer_id', 'common.customer', width: 200),
      ColumnSpec('delivery_date', 'common.due_date', type: FieldType.date, width: 130),
      ColumnSpec('total_amount', 'common.grand_total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('paid_amount', 'status.paid', type: FieldType.decimal, width: 130, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 130),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'customer_id', labelKey: 'common.customer', type: FieldType.reference, required: true, optionsKey: 'list:/customers#name', span: 2),
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'delivery_date', labelKey: 'common.due_date', type: FieldType.date),
      FieldSpec(key: 'warehouse_id', labelKey: 'common.warehouse', type: FieldType.reference, optionsKey: 'list:/warehouses#name'),
      FieldSpec(key: 'payment_term_id', labelKey: 'nav.master_data', type: FieldType.reference, optionsKey: 'lookup:payment-terms'),
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'salesperson_id', labelKey: 'common.created_by', type: FieldType.reference, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'project_id', labelKey: 'nav.project', type: FieldType.reference, optionsKey: 'list:/projects#name'),
      FieldSpec(key: 'discount_percent', labelKey: 'common.discount', type: FieldType.decimal),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[productLine, descriptionLine, quantityLine, priceLine, discountLine, taxLine, warehouseLine],
    extraActions: <DocumentActionSpec>[
      DocumentActionSpec(
        endpoint: 'confirm',
        labelKey: 'action.confirm',
        permissionAction: 'edit',
        icon: Icons.check_circle_outline,
        body: <String, dynamic>{'allow_credit_override': true},
        confirmKey: 'common.confirm',
        visibleWhen: <String>['approved', 'submitted'],
      ),
      DocumentActionSpec(
        endpoint: 'delivery',
        labelKey: 'nav.sales',
        permissionAction: 'create',
        icon: Icons.local_shipping_outlined,
        confirmKey: 'common.confirm',
        visibleWhen: <String>['approved', 'posted', 'partially_fulfilled'],
      ),
      DocumentActionSpec(
        endpoint: 'invoice',
        labelKey: 'nav.accounting',
        permissionAction: 'create',
        icon: Icons.receipt_long_outlined,
        body: <String, dynamic>{'allow_credit_override': true},
        confirmKey: 'common.confirm',
        visibleWhen: <String>['posted', 'partially_fulfilled', 'fulfilled'],
      ),
    ],
  );

  static const DocumentConfig deliveries = DocumentConfig(
    nameKey: 'nav.sales',
    singularKey: 'nav.sales',
    path: '/deliveries',
    permissionPrefix: 'sales.delivery_note',
    icon: Icons.local_shipping_outlined,
    breadcrumbs: <String>['nav.sales', 'nav.sales'],
    linesPath: 'lines',
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('customer_id', 'common.customer', width: 200),
      ColumnSpec('driver_name', 'common.details', width: 160),
      ColumnSpec('status', 'common.status', isStatus: true, width: 120),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'customer_id', labelKey: 'common.customer', type: FieldType.reference, required: true, optionsKey: 'list:/customers#name', span: 2),
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'sales_order_id', labelKey: 'nav.sales', type: FieldType.reference, optionsKey: 'list:/sales-orders#document_no'),
      FieldSpec(key: 'warehouse_id', labelKey: 'common.warehouse', type: FieldType.reference, optionsKey: 'list:/warehouses#name'),
      FieldSpec(key: 'driver_name', labelKey: 'common.details'),
      FieldSpec(key: 'vehicle_number', labelKey: 'common.reference'),
      FieldSpec(key: 'delivery_address', labelKey: 'common.description', span: 2),
    ],
    lineFields: <FieldSpec>[productLine, descriptionLine, quantityLine, priceLine, warehouseLine],
  );

  static const DocumentConfig salesInvoices = DocumentConfig(
    nameKey: 'nav.sales',
    singularKey: 'nav.sales',
    path: '/sales-invoices',
    permissionPrefix: 'sales.sales_invoice',
    icon: Icons.receipt_long_outlined,
    breadcrumbs: <String>['nav.sales', 'nav.sales'],
    linesPath: 'lines',
    totals: <String>['subtotal', 'discount_amount', 'tax_amount', 'total_amount', 'paid_amount', 'balance_amount'],
    statuses: <String>['draft', 'submitted', 'approved', 'rejected', 'posted', 'cancelled'],
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('customer_id', 'common.customer', width: 190),
      ColumnSpec('due_date', 'common.due_date', type: FieldType.date, width: 120),
      ColumnSpec('total_amount', 'common.grand_total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('balance_amount', 'common.balance', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'customer_id', labelKey: 'common.customer', type: FieldType.reference, required: true, optionsKey: 'list:/customers#name', span: 2),
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'due_date', labelKey: 'common.due_date', type: FieldType.date),
      FieldSpec(key: 'sales_order_id', labelKey: 'nav.sales', type: FieldType.reference, optionsKey: 'list:/sales-orders#document_no'),
      FieldSpec(key: 'warehouse_id', labelKey: 'common.warehouse', type: FieldType.reference, optionsKey: 'list:/warehouses#name'),
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'project_id', labelKey: 'nav.project', type: FieldType.reference, optionsKey: 'list:/projects#name'),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[productLine, descriptionLine, quantityLine, priceLine, discountLine, taxLine, warehouseLine],
  );

  static const DocumentConfig creditNotes = DocumentConfig(
    nameKey: 'nav.sales',
    singularKey: 'nav.sales',
    path: '/credit-notes',
    permissionPrefix: 'sales.credit_note',
    icon: Icons.assignment_return_outlined,
    breadcrumbs: <String>['nav.sales', 'nav.sales'],
    linesPath: 'lines',
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('customer_id', 'common.customer', width: 200),
      ColumnSpec('total_amount', 'common.grand_total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('return_reason', 'common.reason', width: 200),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'customer_id', labelKey: 'common.customer', type: FieldType.reference, required: true, optionsKey: 'list:/customers#name', span: 2),
      FieldSpec(key: 'invoice_id', labelKey: 'nav.sales', type: FieldType.reference, optionsKey: 'list:/sales-invoices#document_no'),
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'warehouse_id', labelKey: 'common.warehouse', type: FieldType.reference, optionsKey: 'list:/warehouses#name'),
      FieldSpec(key: 'is_inventory_returned', labelKey: 'nav.inventory', type: FieldType.boolean),
      FieldSpec(key: 'return_reason', labelKey: 'common.reason', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[productLine, descriptionLine, quantityLine, priceLine, taxLine, warehouseLine],
  );

  // ------------------------------------------------------------- purchasing
  static const DocumentConfig purchaseRequests = DocumentConfig(
    nameKey: 'nav.purchasing',
    singularKey: 'nav.purchasing',
    path: '/purchase-requests',
    permissionPrefix: 'purchasing.purchase_request',
    icon: Icons.playlist_add_check_outlined,
    breadcrumbs: <String>['nav.purchasing', 'nav.purchasing'],
    linesPath: 'lines',
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('required_date', 'common.due_date', type: FieldType.date, width: 130),
      ColumnSpec('priority', 'common.status', width: 110),
      ColumnSpec('total_amount', 'common.grand_total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'required_date', labelKey: 'common.due_date', type: FieldType.date),
      FieldSpec(key: 'priority', labelKey: 'common.status', type: FieldType.select, options: <DropdownOption>[
        DropdownOption('low', 'common.none'),
        DropdownOption('normal', 'common.all'),
        DropdownOption('high', 'common.required'),
        DropdownOption('urgent', 'common.required'),
      ]),
      FieldSpec(key: 'cost_center_id', labelKey: 'common.cost_center', type: FieldType.reference, optionsKey: 'lookup:cost-centers'),
      FieldSpec(key: 'project_id', labelKey: 'nav.project', type: FieldType.reference, optionsKey: 'list:/projects#name'),
      FieldSpec(key: 'justification', labelKey: 'common.reason', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[productLine, descriptionLine, quantityLine, priceLine],
  );

  static const DocumentConfig rfqs = DocumentConfig(
    nameKey: 'nav.purchasing',
    singularKey: 'nav.purchasing',
    path: '/rfqs',
    permissionPrefix: 'purchasing.rfq',
    icon: Icons.compare_arrows,
    breadcrumbs: <String>['nav.purchasing', 'nav.purchasing'],
    linesPath: 'lines',
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('closing_date', 'common.due_date', type: FieldType.date, width: 130),
      ColumnSpec('total_amount', 'common.grand_total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'closing_date', labelKey: 'common.due_date', type: FieldType.date),
      FieldSpec(key: 'purchase_request_id', labelKey: 'nav.purchasing', type: FieldType.reference, optionsKey: 'list:/purchase-requests#document_no'),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[productLine, descriptionLine, quantityLine, priceLine],
  );

  static const DocumentConfig supplierQuotations = DocumentConfig(
    nameKey: 'nav.purchasing',
    singularKey: 'nav.purchasing',
    path: '/supplier-quotations',
    permissionPrefix: 'purchasing.supplier_quotation',
    icon: Icons.price_check_outlined,
    breadcrumbs: <String>['nav.purchasing', 'nav.purchasing'],
    linesPath: 'lines',
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('supplier_id', 'common.supplier', width: 200),
      ColumnSpec('total_amount', 'common.grand_total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'supplier_id', labelKey: 'common.supplier', type: FieldType.reference, required: true, optionsKey: 'list:/suppliers#name', span: 2),
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'rfq_id', labelKey: 'nav.purchasing', type: FieldType.reference, optionsKey: 'list:/rfqs#document_no'),
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'reference', labelKey: 'common.reference'),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[productLine, descriptionLine, quantityLine, priceLine, taxLine],
  );

  static const DocumentConfig purchaseOrders = DocumentConfig(
    nameKey: 'nav.purchasing',
    singularKey: 'nav.purchasing',
    path: '/purchase-orders',
    permissionPrefix: 'purchasing.purchase_order',
    icon: Icons.shopping_bag_outlined,
    breadcrumbs: <String>['nav.purchasing', 'nav.purchasing'],
    linesPath: 'lines',
    statuses: <String>['draft', 'submitted', 'approved', 'rejected', 'posted', 'partially_fulfilled', 'fulfilled', 'cancelled'],
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('supplier_id', 'common.supplier', width: 200),
      ColumnSpec('expected_date', 'common.due_date', type: FieldType.date, width: 130),
      ColumnSpec('total_amount', 'common.grand_total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 130),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'supplier_id', labelKey: 'common.supplier', type: FieldType.reference, required: true, optionsKey: 'list:/suppliers#name', span: 2),
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'expected_date', labelKey: 'common.due_date', type: FieldType.date),
      FieldSpec(key: 'warehouse_id', labelKey: 'common.warehouse', type: FieldType.reference, optionsKey: 'list:/warehouses#name'),
      FieldSpec(key: 'payment_term_id', labelKey: 'nav.master_data', type: FieldType.reference, optionsKey: 'lookup:payment-terms'),
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'project_id', labelKey: 'nav.project', type: FieldType.reference, optionsKey: 'list:/projects#name'),
      FieldSpec(key: 'supplier_reference', labelKey: 'common.reference'),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[productLine, descriptionLine, quantityLine, priceLine, discountLine, taxLine, warehouseLine],
    extraActions: <DocumentActionSpec>[
      DocumentActionSpec(
        endpoint: 'receipt',
        labelKey: 'nav.inventory',
        permissionAction: 'create',
        icon: Icons.move_to_inbox_outlined,
        confirmKey: 'common.confirm',
        visibleWhen: <String>['approved', 'partially_fulfilled', 'posted'],
      ),
      DocumentActionSpec(
        endpoint: 'invoice',
        labelKey: 'nav.accounting',
        permissionAction: 'create',
        icon: Icons.receipt_long_outlined,
        confirmKey: 'common.confirm',
        visibleWhen: <String>['posted', 'partially_fulfilled', 'fulfilled'],
      ),
    ],
  );

  static const DocumentConfig goodsReceipts = DocumentConfig(
    nameKey: 'nav.purchasing',
    singularKey: 'nav.purchasing',
    path: '/goods-receipts',
    permissionPrefix: 'purchasing.goods_receipt',
    icon: Icons.move_to_inbox_outlined,
    breadcrumbs: <String>['nav.purchasing', 'nav.purchasing'],
    linesPath: 'lines',
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('supplier_id', 'common.supplier', width: 200),
      ColumnSpec('supplier_delivery_note', 'common.reference', width: 170),
      ColumnSpec('is_invoiced', 'nav.accounting', type: FieldType.boolean, width: 110),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'supplier_id', labelKey: 'common.supplier', type: FieldType.reference, required: true, optionsKey: 'list:/suppliers#name', span: 2),
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'purchase_order_id', labelKey: 'nav.purchasing', type: FieldType.reference, optionsKey: 'list:/purchase-orders#document_no'),
      FieldSpec(key: 'warehouse_id', labelKey: 'common.warehouse', type: FieldType.reference, optionsKey: 'list:/warehouses#name'),
      FieldSpec(key: 'supplier_delivery_note', labelKey: 'common.reference'),
      FieldSpec(key: 'inspection_notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[productLine, descriptionLine, quantityLine, priceLine, warehouseLine],
  );

  static const DocumentConfig purchaseInvoices = DocumentConfig(
    nameKey: 'nav.purchasing',
    singularKey: 'nav.purchasing',
    path: '/purchase-invoices',
    permissionPrefix: 'purchasing.purchase_invoice',
    icon: Icons.receipt_outlined,
    breadcrumbs: <String>['nav.purchasing', 'nav.purchasing'],
    linesPath: 'lines',
    totals: <String>['subtotal', 'discount_amount', 'tax_amount', 'withholding_tax_amount', 'total_amount', 'balance_amount'],
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('supplier_id', 'common.supplier', width: 190),
      ColumnSpec('supplier_invoice_no', 'common.reference', width: 160),
      ColumnSpec('due_date', 'common.due_date', type: FieldType.date, width: 120),
      ColumnSpec('total_amount', 'common.grand_total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'supplier_id', labelKey: 'common.supplier', type: FieldType.reference, required: true, optionsKey: 'list:/suppliers#name', span: 2),
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'due_date', labelKey: 'common.due_date', type: FieldType.date),
      FieldSpec(key: 'supplier_invoice_no', labelKey: 'common.reference'),
      FieldSpec(key: 'supplier_invoice_date', labelKey: 'common.date', type: FieldType.date),
      FieldSpec(key: 'purchase_order_id', labelKey: 'nav.purchasing', type: FieldType.reference, optionsKey: 'list:/purchase-orders#document_no'),
      FieldSpec(key: 'warehouse_id', labelKey: 'common.warehouse', type: FieldType.reference, optionsKey: 'list:/warehouses#name'),
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[productLine, descriptionLine, quantityLine, priceLine, discountLine, taxLine, warehouseLine],
  );

  static const DocumentConfig debitNotes = DocumentConfig(
    nameKey: 'nav.purchasing',
    singularKey: 'nav.purchasing',
    path: '/debit-notes',
    permissionPrefix: 'purchasing.debit_note',
    icon: Icons.assignment_return_outlined,
    breadcrumbs: <String>['nav.purchasing', 'nav.purchasing'],
    linesPath: 'lines',
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('supplier_id', 'common.supplier', width: 200),
      ColumnSpec('total_amount', 'common.grand_total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('return_reason', 'common.reason', width: 190),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'supplier_id', labelKey: 'common.supplier', type: FieldType.reference, required: true, optionsKey: 'list:/suppliers#name', span: 2),
      FieldSpec(key: 'purchase_invoice_id', labelKey: 'nav.purchasing', type: FieldType.reference, optionsKey: 'list:/purchase-invoices#document_no'),
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'warehouse_id', labelKey: 'common.warehouse', type: FieldType.reference, optionsKey: 'list:/warehouses#name'),
      FieldSpec(key: 'is_inventory_returned', labelKey: 'nav.inventory', type: FieldType.boolean),
      FieldSpec(key: 'return_reason', labelKey: 'common.reason', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[productLine, descriptionLine, quantityLine, priceLine, taxLine, warehouseLine],
  );

  // -------------------------------------------------------------- inventory
  static const DocumentConfig stockAdjustments = DocumentConfig(
    nameKey: 'nav.inventory',
    singularKey: 'nav.inventory',
    path: '/stock-adjustments',
    permissionPrefix: 'inventory.stock_adjustment',
    icon: Icons.tune,
    breadcrumbs: <String>['nav.inventory', 'nav.inventory'],
    dateField: 'adjustment_date',
    linesPath: 'lines',
    headerFields: <FieldSpec>[
      FieldSpec(key: 'warehouse_id', labelKey: 'common.warehouse', type: FieldType.reference, required: true, optionsKey: 'list:/warehouses#name'),
      FieldSpec(key: 'adjustment_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'adjustment_type', labelKey: 'common.status', type: FieldType.select, options: <DropdownOption>[
        DropdownOption('increase', 'status.posted'),
        DropdownOption('decrease', 'status.cancelled'),
        DropdownOption('revaluation', 'dash.stock_value'),
      ]),
      FieldSpec(key: 'reason', labelKey: 'common.reason', required: true),
      FieldSpec(key: 'offset_account_id', labelKey: 'nav.accounting', type: FieldType.reference, optionsKey: 'list:/accounts#name'),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[
      productLine,
      quantityLine,
      FieldSpec(
        key: 'direction',
        labelKey: 'common.status',
        type: FieldType.select,
        options: <DropdownOption>[
          DropdownOption('in', 'common.debit'),
          DropdownOption('out', 'common.credit'),
        ],
        defaultValue: 'in',
      ),
      FieldSpec(key: 'unit_cost', labelKey: 'common.price', type: FieldType.decimal),
      FieldSpec(key: 'batch_id', labelKey: 'nav.inventory', type: FieldType.reference, optionsKey: 'list:/batches#batch_no'),
      FieldSpec(key: 'notes', labelKey: 'common.notes'),
    ],
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('adjustment_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('warehouse_id', 'common.warehouse', width: 170),
      ColumnSpec('adjustment_type', 'common.status', width: 130),
      ColumnSpec('total_cost', 'common.total', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
  );

  static const DocumentConfig stockTransfers = DocumentConfig(
    nameKey: 'nav.inventory',
    singularKey: 'nav.inventory',
    path: '/stock-transfers',
    permissionPrefix: 'inventory.stock_transfer',
    icon: Icons.swap_horiz,
    breadcrumbs: <String>['nav.inventory', 'nav.inventory'],
    dateField: 'transfer_date',
    linesPath: 'lines',
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('transfer_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('source_warehouse_id', 'common.from', width: 170),
      ColumnSpec('destination_warehouse_id', 'common.to', width: 170),
      ColumnSpec('total_cost', 'common.total', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'source_warehouse_id', labelKey: 'common.from', type: FieldType.reference, required: true, optionsKey: 'list:/warehouses#name'),
      FieldSpec(key: 'destination_warehouse_id', labelKey: 'common.to', type: FieldType.reference, required: true, optionsKey: 'list:/warehouses#name'),
      FieldSpec(key: 'transfer_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[productLine, quantityLine, warehouseLine],
  );

  static const DocumentConfig stockCounts = DocumentConfig(
    nameKey: 'nav.inventory',
    singularKey: 'nav.inventory',
    path: '/stock-counts',
    permissionPrefix: 'inventory.stock_count',
    icon: Icons.fact_check_outlined,
    breadcrumbs: <String>['nav.inventory', 'nav.inventory'],
    dateField: 'count_date',
    linesPath: 'lines',
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('count_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('warehouse_id', 'common.warehouse', width: 180),
      ColumnSpec('count_type', 'common.status', width: 130),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'warehouse_id', labelKey: 'common.warehouse', type: FieldType.reference, required: true, optionsKey: 'list:/warehouses#name'),
      FieldSpec(key: 'count_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'responsible_id', labelKey: 'common.employee', type: FieldType.reference, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[
      productLine,
      FieldSpec(key: 'counted_quantity', labelKey: 'common.quantity', type: FieldType.decimal, required: true),
      FieldSpec(key: 'unit_cost', labelKey: 'common.price', type: FieldType.decimal),
    ],
  );

  // ------------------------------------------------------------- accounting
  static const DocumentConfig journalEntries = DocumentConfig(
    nameKey: 'nav.accounting',
    singularKey: 'nav.accounting',
    path: '/journal-entries',
    permissionPrefix: 'accounting.journal_entry',
    icon: Icons.menu_book_outlined,
    breadcrumbs: <String>['nav.accounting', 'nav.accounting'],
    dateField: 'entry_date',
    linesPath: 'lines',
    totals: <String>['total_debit', 'total_credit'],
    columns: <ColumnSpec>[
      ColumnSpec('entry_no', 'common.document_no', width: 140, emphasize: true),
      ColumnSpec('entry_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('reference', 'common.reference', width: 160),
      ColumnSpec('description', 'common.description', width: 220),
      ColumnSpec('total_debit', 'common.debit', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('total_credit', 'common.credit', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'entry_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'entry_type', labelKey: 'common.status', type: FieldType.select, options: <DropdownOption>[
        DropdownOption('manual', 'common.edit'),
        DropdownOption('opening', 'status.open'),
        DropdownOption('adjustment', 'nav.accounting'),
        DropdownOption('closing', 'status.closed'),
      ], defaultValue: 'manual'),
      FieldSpec(key: 'reference', labelKey: 'common.reference'),
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'description', labelKey: 'common.description', span: 2),
    ],
    lineFields: <FieldSpec>[
      FieldSpec(
        key: 'account_id',
        labelKey: 'nav.accounting',
        type: FieldType.reference,
        required: true,
        optionsKey: 'list:/accounts#name',
        span: 2,
      ),
      FieldSpec(key: 'description', labelKey: 'common.description', span: 2),
      FieldSpec(key: 'debit', labelKey: 'common.debit', type: FieldType.decimal),
      FieldSpec(key: 'credit', labelKey: 'common.credit', type: FieldType.decimal),
      FieldSpec(key: 'cost_center_id', labelKey: 'common.cost_center', type: FieldType.reference, optionsKey: 'lookup:cost-centers'),
      FieldSpec(key: 'party_type', labelKey: 'common.party', type: FieldType.select, options: <DropdownOption>[
        DropdownOption('customer', 'common.customer'),
        DropdownOption('supplier', 'common.supplier'),
      ]),
      FieldSpec(key: 'party_id', labelKey: 'common.party'),
    ],
  );

  // --------------------------------------------------------------- treasury
  static const DocumentConfig payments = DocumentConfig(
    nameKey: 'nav.treasury',
    singularKey: 'nav.treasury',
    path: '/payments',
    permissionPrefix: 'treasury.payment',
    icon: Icons.payments_outlined,
    breadcrumbs: <String>['nav.treasury', 'nav.treasury'],
    linesPath: 'lines',
    totals: <String>['amount', 'allocated_amount', 'unallocated_amount', 'withholding_amount'],
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('direction', 'common.status', width: 110),
      ColumnSpec('party_name', 'common.party', width: 190),
      ColumnSpec('payment_method', 'pos.payment_method', width: 130),
      ColumnSpec('amount', 'common.amount', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'direction', labelKey: 'common.status', type: FieldType.select, options: <DropdownOption>[
        DropdownOption('inbound', 'common.debit'),
        DropdownOption('outbound', 'common.credit'),
      ], required: true),
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'party_type', labelKey: 'common.party', type: FieldType.select, options: <DropdownOption>[
        DropdownOption('customer', 'common.customer'),
        DropdownOption('supplier', 'common.supplier'),
        DropdownOption('employee', 'common.employee'),
        DropdownOption('other', 'common.none'),
      ]),
      FieldSpec(key: 'party_id', labelKey: 'common.party'),
      FieldSpec(key: 'amount', labelKey: 'common.amount', type: FieldType.decimal, required: true),
      FieldSpec(key: 'payment_method', labelKey: 'pos.payment_method', type: FieldType.select, options: <DropdownOption>[
        DropdownOption('cash', 'pos.cash'),
        DropdownOption('bank_transfer', 'nav.treasury'),
        DropdownOption('cheque', 'nav.treasury'),
        DropdownOption('card', 'pos.card'),
      ], defaultValue: 'cash'),
      FieldSpec(key: 'cash_account_id', labelKey: 'nav.treasury', type: FieldType.reference, optionsKey: 'list:/cash-accounts#name'),
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'reference', labelKey: 'common.reference'),
      FieldSpec(key: 'description', labelKey: 'common.description', span: 2),
    ],
    lineFields: <FieldSpec>[],
    extraActions: <DocumentActionSpec>[
      DocumentActionSpec(
        endpoint: 'allocate',
        labelKey: 'action.confirm',
        permissionAction: 'edit',
        icon: Icons.link,
        visibleWhen: <String>['posted'],
      ),
    ],
  );

  static const DocumentConfig treasuryTransfers = DocumentConfig(
    nameKey: 'nav.treasury',
    singularKey: 'nav.treasury',
    path: '/transfers',
    permissionPrefix: 'treasury.treasury_transfer',
    icon: Icons.compare_arrows,
    breadcrumbs: <String>['nav.treasury', 'nav.treasury'],
    linesPath: 'lines',
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('amount', 'common.amount', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('reference', 'common.reference', width: 170),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'amount', labelKey: 'common.amount', type: FieldType.decimal, required: true),
      FieldSpec(key: 'from_cash_account_id', labelKey: 'common.from', type: FieldType.reference, optionsKey: 'list:/cash-accounts#name'),
      FieldSpec(key: 'to_cash_account_id', labelKey: 'common.to', type: FieldType.reference, optionsKey: 'list:/cash-accounts#name'),
      FieldSpec(key: 'reference', labelKey: 'common.reference'),
      FieldSpec(key: 'description', labelKey: 'common.description', span: 2),
    ],
    lineFields: <FieldSpec>[],
  );

  // ------------------------------------------------- expenses and assets
  static const DocumentConfig expenses = DocumentConfig(
    nameKey: 'nav.expenses',
    singularKey: 'nav.expenses',
    path: '/expenses',
    permissionPrefix: 'expenses.expense',
    icon: Icons.payments_outlined,
    breadcrumbs: <String>['nav.expenses', 'nav.expenses'],
    linesPath: 'lines',
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('payee_name', 'common.party', width: 190),
      ColumnSpec('total_amount', 'common.grand_total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('is_paid', 'status.paid', type: FieldType.boolean, width: 100),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'category_id', labelKey: 'nav.expenses', type: FieldType.reference, optionsKey: 'list:/expense-categories#name'),
      FieldSpec(key: 'payee_type', labelKey: 'common.party', type: FieldType.select, options: <DropdownOption>[
        DropdownOption('employee', 'common.employee'),
        DropdownOption('supplier', 'common.supplier'),
        DropdownOption('customer', 'common.customer'),
        DropdownOption('other', 'common.none'),
      ]),
      FieldSpec(key: 'payee_name', labelKey: 'common.name'),
      FieldSpec(key: 'project_id', labelKey: 'nav.project', type: FieldType.reference, optionsKey: 'list:/projects#name'),
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'supplier_invoice_no', labelKey: 'common.reference'),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[
      FieldSpec(key: 'description', labelKey: 'common.description', required: true, span: 2),
      FieldSpec(key: 'quantity', labelKey: 'common.quantity', type: FieldType.decimal, defaultValue: 1),
      FieldSpec(key: 'unit_price', labelKey: 'common.unit_price', type: FieldType.decimal, required: true),
      FieldSpec(key: 'expense_account_id', labelKey: 'nav.accounting', type: FieldType.reference, optionsKey: 'list:/accounts#name'),
      FieldSpec(key: 'cost_center_id', labelKey: 'common.cost_center', type: FieldType.reference, optionsKey: 'lookup:cost-centers'),
      FieldSpec(key: 'tax_id', labelKey: 'common.tax', type: FieldType.reference, optionsKey: 'lookup:taxes'),
    ],
  );

  static const DocumentConfig expenseClaims = DocumentConfig(
    nameKey: 'nav.expenses',
    singularKey: 'nav.expenses',
    path: '/expense-claims',
    permissionPrefix: 'expenses.expense_claim',
    icon: Icons.assignment_turned_in_outlined,
    breadcrumbs: <String>['nav.expenses', 'nav.expenses'],
    linesPath: 'lines',
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('employee_id', 'common.employee', width: 190),
      ColumnSpec('total_amount', 'common.grand_total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'employee_id', labelKey: 'common.employee', type: FieldType.reference, required: true, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'project_id', labelKey: 'nav.project', type: FieldType.reference, optionsKey: 'list:/projects#name'),
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[
      FieldSpec(key: 'expense_date', labelKey: 'common.date', type: FieldType.date, required: true),
      FieldSpec(key: 'description', labelKey: 'common.description', required: true, span: 2),
      FieldSpec(key: 'amount', labelKey: 'common.amount', type: FieldType.decimal, required: true),
      FieldSpec(key: 'category_id', labelKey: 'nav.expenses', type: FieldType.reference, optionsKey: 'list:/expense-categories#name'),
      FieldSpec(key: 'cost_center_id', labelKey: 'common.cost_center', type: FieldType.reference, optionsKey: 'lookup:cost-centers'),
    ],
  );

  static const DocumentConfig advances = DocumentConfig(
    nameKey: 'nav.expenses',
    singularKey: 'nav.expenses',
    path: '/advances',
    permissionPrefix: 'expenses.expense_advance',
    icon: Icons.request_quote_outlined,
    breadcrumbs: <String>['nav.expenses', 'nav.expenses'],
    linesPath: 'lines',
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('employee_id', 'common.employee', width: 190),
      ColumnSpec('total_amount', 'common.grand_total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'employee_id', labelKey: 'common.employee', type: FieldType.reference, required: true, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'amount', labelKey: 'common.amount', type: FieldType.decimal, required: true),
      FieldSpec(key: 'purpose', labelKey: 'common.reason', span: 2),
    ],
    lineFields: <FieldSpec>[],
  );

  static const DocumentConfig assetTransfers = DocumentConfig(
    nameKey: 'nav.assets',
    singularKey: 'nav.assets',
    path: '/asset-transfers',
    permissionPrefix: 'assets.asset_transfer',
    icon: Icons.moving,
    breadcrumbs: <String>['nav.assets', 'nav.assets'],
    linesPath: 'lines',
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('asset_id', 'nav.assets', width: 190),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'asset_id', labelKey: 'nav.assets', type: FieldType.reference, required: true, optionsKey: 'list:/assets#name'),
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'to_branch_id', labelKey: 'common.branch', type: FieldType.reference, optionsKey: 'lookup:branches'),
      FieldSpec(key: 'to_location', labelKey: 'common.details'),
      FieldSpec(key: 'reason', labelKey: 'common.reason', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[],
  );

  static const DocumentConfig assetDisposals = DocumentConfig(
    nameKey: 'nav.assets',
    singularKey: 'nav.assets',
    path: '/asset-disposals',
    permissionPrefix: 'assets.asset_disposal',
    icon: Icons.delete_sweep_outlined,
    breadcrumbs: <String>['nav.assets', 'nav.assets'],
    linesPath: 'lines',
    totals: <String>['proceeds_amount', 'gain_loss_amount'],
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('asset_id', 'nav.assets', width: 190),
      ColumnSpec('disposal_type', 'common.status', width: 140),
      ColumnSpec('proceeds_amount', 'common.amount', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'asset_id', labelKey: 'nav.assets', type: FieldType.reference, required: true, optionsKey: 'list:/assets#name'),
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'disposal_type', labelKey: 'common.status', type: FieldType.select, options: <DropdownOption>[
        DropdownOption('sale', 'nav.sales'),
        DropdownOption('scrap', 'status.cancelled'),
        DropdownOption('donation', 'common.none'),
        DropdownOption('write_off', 'status.rejected'),
      ], required: true),
      FieldSpec(key: 'proceeds_amount', labelKey: 'common.amount', type: FieldType.decimal),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[],
  );

  // ------------------------------------------------------- people/operations
  static const DocumentConfig leaveRequests = DocumentConfig(
    nameKey: 'nav.hr',
    singularKey: 'nav.hr',
    path: '/leave-requests',
    permissionPrefix: 'hr.leave_request',
    icon: Icons.event_busy_outlined,
    breadcrumbs: <String>['nav.hr', 'nav.hr'],
    linesPath: 'lines',
    dateField: 'start_date',
    columns: <ColumnSpec>[
      ColumnSpec('request_no', 'common.document_no', width: 140, emphasize: true),
      ColumnSpec('employee_id', 'common.employee', width: 190),
      ColumnSpec('leave_type_id', 'nav.hr', width: 160),
      ColumnSpec('start_date', 'common.from', type: FieldType.date, width: 130),
      ColumnSpec('end_date', 'common.to', type: FieldType.date, width: 130),
      ColumnSpec('total_days', 'common.quantity', type: FieldType.decimal, width: 110, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'employee_id', labelKey: 'common.employee', type: FieldType.reference, required: true, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'leave_type_id', labelKey: 'nav.hr', type: FieldType.reference, required: true, optionsKey: 'list:/leave-type-master#name'),
      FieldSpec(key: 'start_date', labelKey: 'common.from', type: FieldType.date, required: true),
      FieldSpec(key: 'end_date', labelKey: 'common.to', type: FieldType.date, required: true),
      FieldSpec(key: 'is_half_day', labelKey: 'common.yes', type: FieldType.boolean),
      FieldSpec(key: 'reason', labelKey: 'common.reason', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[],
  );

  static const DocumentConfig timesheets = DocumentConfig(
    nameKey: 'nav.project',
    singularKey: 'nav.project',
    path: '/timesheets',
    permissionPrefix: 'projects.timesheet',
    icon: Icons.timer_outlined,
    breadcrumbs: <String>['nav.project', 'nav.project'],
    linesPath: 'lines',
    dateField: 'period_start',
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 140, emphasize: true),
      ColumnSpec('employee_id', 'common.employee', width: 180),
      ColumnSpec('project_id', 'nav.project', width: 180),
      ColumnSpec('period_start', 'common.from', type: FieldType.date, width: 120),
      ColumnSpec('total_hours', 'common.quantity', type: FieldType.decimal, width: 120, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'employee_id', labelKey: 'common.employee', type: FieldType.reference, required: true, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'project_id', labelKey: 'nav.project', type: FieldType.reference, optionsKey: 'list:/projects#name'),
      FieldSpec(key: 'period_start', labelKey: 'common.from', type: FieldType.date, required: true),
      FieldSpec(key: 'period_end', labelKey: 'common.to', type: FieldType.date, required: true),
      FieldSpec(key: 'hourly_rate', labelKey: 'common.price', type: FieldType.decimal),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[
      FieldSpec(key: 'work_date', labelKey: 'common.date', type: FieldType.date, required: true),
      FieldSpec(key: 'hours', labelKey: 'common.quantity', type: FieldType.decimal, required: true),
      FieldSpec(key: 'task_id', labelKey: 'nav.project', type: FieldType.reference, optionsKey: 'list:/project-tasks#name'),
      FieldSpec(key: 'description', labelKey: 'common.description', span: 2),
      FieldSpec(key: 'is_billable', labelKey: 'nav.sales', type: FieldType.boolean),
    ],
  );

  static const DocumentConfig productionOrders = DocumentConfig(
    nameKey: 'nav.manufacturing',
    singularKey: 'nav.manufacturing',
    path: '/production-orders',
    permissionPrefix: 'manufacturing.production_order',
    icon: Icons.factory_outlined,
    breadcrumbs: <String>['nav.manufacturing', 'nav.manufacturing'],
    linesPath: 'materials',
    totals: <String>['material_cost', 'labour_cost', 'overhead_cost', 'total_cost'],
    statuses: <String>['draft', 'planned', 'released', 'in_progress', 'completed', 'cancelled'],
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('product_id', 'common.product', width: 190),
      ColumnSpec('planned_quantity', 'common.quantity', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('produced_quantity', 'common.quantity', type: FieldType.decimal, width: 140, align: MainAxisAlignment.end),
      ColumnSpec('planned_start_date', 'common.from', type: FieldType.date, width: 130),
      ColumnSpec('status', 'common.status', isStatus: true, width: 120),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'product_id', labelKey: 'common.product', type: FieldType.reference, required: true, optionsKey: 'list:/products#name', span: 2),
      FieldSpec(key: 'bom_id', labelKey: 'nav.manufacturing', type: FieldType.reference, optionsKey: 'list:/boms#code'),
      FieldSpec(key: 'warehouse_id', labelKey: 'common.warehouse', type: FieldType.reference, optionsKey: 'list:/warehouses#name'),
      FieldSpec(key: 'planned_quantity', labelKey: 'common.quantity', type: FieldType.decimal, required: true),
      FieldSpec(key: 'planned_start_date', labelKey: 'common.from', type: FieldType.date),
      FieldSpec(key: 'planned_end_date', labelKey: 'common.to', type: FieldType.date),
      FieldSpec(key: 'priority', labelKey: 'common.status', type: FieldType.select, options: <DropdownOption>[
        DropdownOption('low', 'common.none'),
        DropdownOption('normal', 'common.all'),
        DropdownOption('high', 'common.required'),
      ]),
      FieldSpec(key: 'notes', labelKey: 'common.notes', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[productLine, quantityLine, warehouseLine],
  );

  static const DocumentConfig workOrders = DocumentConfig(
    nameKey: 'nav.service',
    singularKey: 'nav.service',
    path: '/work-orders',
    permissionPrefix: 'service.work_order',
    icon: Icons.handyman_outlined,
    breadcrumbs: <String>['nav.service', 'nav.service'],
    linesPath: 'parts',
    dateField: 'scheduled_date',
    totals: <String>['labour_amount', 'parts_amount', 'expenses_amount'],
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('customer_id', 'common.customer', width: 190),
      ColumnSpec('scheduled_date', 'common.date', type: FieldType.date, width: 130),
      ColumnSpec('technician_id', 'common.employee', width: 170),
      ColumnSpec('priority', 'common.status', width: 110),
      ColumnSpec('status', 'common.status', isStatus: true, width: 120),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'customer_id', labelKey: 'common.customer', type: FieldType.reference, required: true, optionsKey: 'list:/customers#name', span: 2),
      FieldSpec(key: 'technician_id', labelKey: 'common.employee', type: FieldType.reference, optionsKey: 'list:/employees#full_name'),
      FieldSpec(key: 'scheduled_date', labelKey: 'common.date', type: FieldType.date, required: true),
      FieldSpec(key: 'priority', labelKey: 'common.status', type: FieldType.select, options: <DropdownOption>[
        DropdownOption('low', 'common.none'),
        DropdownOption('normal', 'common.all'),
        DropdownOption('high', 'common.required'),
        DropdownOption('urgent', 'common.required'),
      ]),
      FieldSpec(key: 'problem_description', labelKey: 'common.description', type: FieldType.multiline, span: 2),
      FieldSpec(key: 'site_address', labelKey: 'common.details', span: 2),
    ],
    lineFields: <FieldSpec>[productLine, quantityLine, priceLine],
  );

  static const DocumentConfig serviceContracts = DocumentConfig(
    nameKey: 'nav.service',
    singularKey: 'nav.service',
    path: '/contracts',
    permissionPrefix: 'service.service_contract',
    icon: Icons.article_outlined,
    breadcrumbs: <String>['nav.service', 'nav.service'],
    linesPath: 'assets',
    columns: <ColumnSpec>[
      ColumnSpec('document_no', 'common.document_no', width: 150, emphasize: true),
      ColumnSpec('customer_id', 'common.customer', width: 200),
      ColumnSpec('document_date', 'common.date', type: FieldType.date, width: 120),
      ColumnSpec('total_amount', 'common.grand_total', type: FieldType.decimal, width: 150, align: MainAxisAlignment.end),
      ColumnSpec('status', 'common.status', isStatus: true, width: 120),
    ],
    headerFields: <FieldSpec>[
      FieldSpec(key: 'customer_id', labelKey: 'common.customer', type: FieldType.reference, required: true, optionsKey: 'list:/customers#name', span: 2),
      FieldSpec(key: 'document_date', labelKey: 'common.document_date', type: FieldType.date, required: true),
      FieldSpec(key: 'total_amount', labelKey: 'common.grand_total', type: FieldType.decimal),
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'terms_and_conditions', labelKey: 'common.description', type: FieldType.multiline, span: 2),
    ],
    lineFields: <FieldSpec>[
      FieldSpec(key: 'asset_id', labelKey: 'nav.assets', type: FieldType.reference, optionsKey: 'list:/assets#name'),
      FieldSpec(key: 'price', labelKey: 'common.price', type: FieldType.decimal),
    ],
  );
}
