"""Domain enumerations shared by models, schemas and services.

Values are stored as short strings so migrations stay flexible across
databases (no native PostgreSQL ENUM types to alter).
"""

from __future__ import annotations

from enum import Enum


# StrEnum is intentionally built on Enum: it adds ``values()``/``has()`` helpers used by
# the validators.  (UP042 only suggests the stdlib class, which lacks those helpers.)
class StrEnum(str, Enum):  # noqa: UP042
    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.value

    @classmethod
    def values(cls) -> list[str]:
        return [member.value for member in cls]

    @classmethod
    def has(cls, value: str) -> bool:
        return value in cls.values()


class DocumentStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    POSTED = "posted"
    PARTIALLY_FULFILLED = "partially_fulfilled"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
    CLOSED = "closed"


class PaymentStatus(StrEnum):
    UNPAID = "unpaid"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERPAID = "overpaid"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class AccountType(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


class NormalBalance(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class PartyType(StrEnum):
    CUSTOMER = "customer"
    SUPPLIER = "supplier"
    EMPLOYEE = "employee"
    OTHER = "other"


class ProductType(StrEnum):
    STOCK = "stock"
    SERVICE = "service"
    CONSUMABLE = "consumable"
    ASSET = "asset"
    KIT = "kit"
    BUNDLE = "bundle"


class ValuationMethod(StrEnum):
    FIFO = "fifo"
    AVERAGE = "average"
    STANDARD = "standard"


class MovementType(StrEnum):
    OPENING = "opening"
    RECEIPT = "receipt"
    ISSUE = "issue"
    TRANSFER_OUT = "transfer_out"
    TRANSFER_IN = "transfer_in"
    ADJUSTMENT_IN = "adjustment_in"
    ADJUSTMENT_OUT = "adjustment_out"
    PRODUCTION_IN = "production_in"
    PRODUCTION_OUT = "production_out"
    SALES_RETURN_IN = "sales_return_in"
    PURCHASE_RETURN_OUT = "purchase_return_out"
    SCRAP = "scrap"
    CONSUMPTION = "consumption"


INBOUND_MOVEMENTS = {
    MovementType.OPENING,
    MovementType.RECEIPT,
    MovementType.TRANSFER_IN,
    MovementType.ADJUSTMENT_IN,
    MovementType.PRODUCTION_IN,
    MovementType.SALES_RETURN_IN,
}

OUTBOUND_MOVEMENTS = {
    MovementType.ISSUE,
    MovementType.TRANSFER_OUT,
    MovementType.ADJUSTMENT_OUT,
    MovementType.PRODUCTION_OUT,
    MovementType.PURCHASE_RETURN_OUT,
    MovementType.SCRAP,
    MovementType.CONSUMPTION,
}


class DepreciationMethod(StrEnum):
    STRAIGHT_LINE = "straight_line"
    DECLINING_BALANCE = "declining_balance"
    DOUBLE_DECLINING = "double_declining"
    UNITS_OF_PRODUCTION = "units_of_production"
    NONE = "none"


class AssetStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    FULLY_DEPRECIATED = "fully_depreciated"
    DISPOSED = "disposed"
    UNDER_MAINTENANCE = "under_maintenance"


class PaymentMethod(StrEnum):
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    CHEQUE = "cheque"
    CARD = "card"
    CREDIT = "credit"
    MOBILE_WALLET = "mobile_wallet"
    OTHER = "other"


class PaymentDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CashFlowCategory(StrEnum):
    OPERATING = "operating"
    INVESTING = "investing"
    FINANCING = "financing"


class TaxType(StrEnum):
    SALES = "sales"
    PURCHASE = "purchase"
    WITHHOLDING = "withholding"
    EXCISE = "excise"
    CUSTOM = "custom"


class TaxComputation(StrEnum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"


class TaxInclusion(StrEnum):
    EXCLUSIVE = "exclusive"
    INCLUSIVE = "inclusive"


class LeadStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"


class OpportunityStage(StrEnum):
    NEW = "new"
    QUALIFICATION = "qualification"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"


class ActivityType(StrEnum):
    CALL = "call"
    MEETING = "meeting"
    EMAIL = "email"
    VISIT = "visit"
    TASK = "task"
    NOTE = "note"
    FOLLOW_UP = "follow_up"


class ActivityStatus(StrEnum):
    PLANNED = "planned"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    PLANNED = "planned"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEW = "review"
    DONE = "done"
    CANCELLED = "cancelled"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class BillingMethod(StrEnum):
    FIXED_PRICE = "fixed_price"
    TIME_AND_MATERIAL = "time_and_material"
    MILESTONE = "milestone"
    NON_BILLABLE = "non_billable"


class EmployeeStatus(StrEnum):
    ACTIVE = "active"
    PROBATION = "probation"
    SUSPENDED = "suspended"
    ON_LEAVE = "on_leave"
    RESIGNED = "resigned"
    TERMINATED = "terminated"
    RETIRED = "retired"


class ContractType(StrEnum):
    PERMANENT = "permanent"
    FIXED_TERM = "fixed_term"
    PART_TIME = "part_time"
    CONTRACTOR = "contractor"
    INTERN = "intern"


class AttendanceStatus(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    EARLY_LEAVE = "early_leave"
    ON_LEAVE = "on_leave"
    HOLIDAY = "holiday"
    WEEKEND = "weekend"
    REMOTE = "remote"


class LeaveStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class SalaryComponentType(StrEnum):
    BASIC = "basic"
    ALLOWANCE = "allowance"
    DEDUCTION = "deduction"
    OVERTIME = "overtime"
    BONUS = "bonus"
    TAX = "tax"
    INSURANCE = "insurance"
    EMPLOYER_CONTRIBUTION = "employer_contribution"


class SalaryCalculationType(StrEnum):
    FIXED = "fixed"
    PERCENTAGE_OF_BASIC = "percentage_of_basic"
    FORMULA = "formula"
    HOURLY = "hourly"


class PayrollStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    POSTED = "posted"
    PAID = "paid"
    CANCELLED = "cancelled"


class ProductionStatus(StrEnum):
    DRAFT = "draft"
    PLANNED = "planned"
    RELEASED = "released"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TicketStatus(StrEnum):
    NEW = "new"
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    WAITING_CUSTOMER = "waiting_customer"
    WAITING_PARTS = "waiting_parts"
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class WorkOrderType(StrEnum):
    INSTALLATION = "installation"
    MAINTENANCE = "maintenance"
    REPAIR = "repair"
    INSPECTION = "inspection"
    WARRANTY = "warranty"
    OTHER = "other"


class ServiceContractStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class WorkflowTriggerType(StrEnum):
    DOCUMENT_CREATED = "document_created"
    DOCUMENT_SUBMITTED = "document_submitted"
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class WorkflowStepType(StrEnum):
    APPROVAL = "approval"
    CONDITION = "condition"
    NOTIFICATION = "notification"
    AUTO_APPROVE = "auto_approve"
    ACTION = "action"


class WorkflowInstanceStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class WorkflowActionType(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    RETURN = "return"
    DELEGATE = "delegate"
    COMMENT = "comment"
    CANCEL = "cancel"


class NotificationType(StrEnum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    APPROVAL = "approval"
    SYSTEM = "system"
    REMINDER = "reminder"


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    WHATSAPP = "whatsapp"


class AuditAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    RESTORE = "restore"
    APPROVE = "approve"
    REJECT = "reject"
    SUBMIT = "submit"
    POST = "post"
    UNPOST = "unpost"
    CANCEL = "cancel"
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    PERMISSION_CHANGE = "permission_change"
    EXPORT = "export"
    IMPORT = "import"
    BACKUP = "backup"
    RESTORE_BACKUP = "restore_backup"
    PRINT = "print"
    VIEW = "view"
    CLOSE = "close"


class ImportStatus(StrEnum):
    UPLOADED = "uploaded"
    MAPPED = "mapped"
    VALIDATED = "validated"
    IMPORTED = "imported"
    FAILED = "failed"


class ShiftStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    RECONCILED = "reconciled"


class BankReconciliationStatus(StrEnum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AddressType(StrEnum):
    BILLING = "billing"
    SHIPPING = "shipping"
    HOME = "home"
    WORK = "work"
    OTHER = "other"


class CurrencyRateType(StrEnum):
    SPOT = "spot"
    AVERAGE = "average"
    HISTORICAL = "historical"
    CLOSING = "closing"


class ModuleKey(StrEnum):
    """Modules a company can enable or disable."""

    CORE = "core"
    CRM = "crm"
    SUPPLIERS = "suppliers"
    INVENTORY = "inventory"
    PURCHASING = "purchasing"
    SALES = "sales"
    POS = "pos"
    ACCOUNTING = "accounting"
    TREASURY = "treasury"
    TAX = "tax"
    ASSETS = "assets"
    EXPENSES = "expenses"
    HR = "hr"
    PAYROLL = "payroll"
    MANUFACTURING = "manufacturing"
    PROJECTS = "projects"
    SERVICE = "service"
    REPORTS = "reports"
    WORKFLOW = "workflow"
    NOTIFICATIONS = "notifications"
    DOCUMENTS = "documents"
    IMPORT_EXPORT = "import_export"
