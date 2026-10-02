enum ProjectStatus {
  pending('pending'),
  inProgress('in_progress'),
  completed('completed'),
  cancelled('cancelled');

  final String value;
  const ProjectStatus(this.value);

  static ProjectStatus fromString(String value) {
    return ProjectStatus.values.firstWhere(
      (e) => e.value == value,
      orElse: () => ProjectStatus.pending,
    );
  }
}

class Project {
  final int? id;
  final int quoteId;
  final String status;
  final DateTime? startDate;
  final DateTime? endDate;
  final double progressPercent;
  final DateTime createdAt;

  const Project({
    this.id,
    required this.quoteId,
    this.status = 'pending',
    this.startDate,
    this.endDate,
    this.progressPercent = 0,
    required this.createdAt,
  });

  factory Project.create({
    required int quoteId,
    String status = 'pending',
    DateTime? startDate,
    DateTime? endDate,
    double progressPercent = 0,
  }) {
    return Project(
      quoteId: quoteId,
      status: status,
      startDate: startDate,
      endDate: endDate,
      progressPercent: progressPercent,
      createdAt: DateTime.now(),
    );
  }

  Project copyWith({
    int? id,
    int? quoteId,
    String? status,
    DateTime? startDate,
    DateTime? endDate,
    double? progressPercent,
    DateTime? createdAt,
  }) {
    return Project(
      id: id ?? this.id,
      quoteId: quoteId ?? this.quoteId,
      status: status ?? this.status,
      startDate: startDate ?? this.startDate,
      endDate: endDate ?? this.endDate,
      progressPercent: progressPercent ?? this.progressPercent,
      createdAt: createdAt ?? this.createdAt,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      if (id != null) 'id': id,
      'quoteId': quoteId,
      'status': status,
      'startDate': startDate?.toIso8601String(),
      'endDate': endDate?.toIso8601String(),
      'progressPercent': progressPercent,
      'createdAt': createdAt.toIso8601String(),
    };
  }

  factory Project.fromMap(Map<String, dynamic> map) {
    return Project(
      id: map['id'] as int?,
      quoteId: map['quoteId'] as int,
      status: map['status'] as String? ?? 'pending',
      startDate: map['startDate'] != null ? DateTime.parse(map['startDate'] as String) : null,
      endDate: map['endDate'] != null ? DateTime.parse(map['endDate'] as String) : null,
      progressPercent: (map['progressPercent'] as num?)?.toDouble() ?? 0,
      createdAt: DateTime.parse(map['createdAt'] as String),
    );
  }

  Map<String, dynamic> toJson() => toMap();

  factory Project.fromJson(Map<String, dynamic> json) => Project.fromMap(json);

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Project &&
          runtimeType == other.runtimeType &&
          id == other.id &&
          quoteId == other.quoteId &&
          status == other.status &&
          startDate == other.startDate &&
          endDate == other.endDate &&
          progressPercent == other.progressPercent &&
          createdAt == other.createdAt;

  @override
  int get hashCode {
    return Object.hash(
      id,
      quoteId,
      status,
      startDate,
      endDate,
      progressPercent,
      createdAt,
    );
  }

  @override
  String toString() {
    return 'Project(id: $id, quoteId: $quoteId, status: $status, startDate: $startDate, endDate: $endDate, progressPercent: $progressPercent, createdAt: $createdAt)';
  }
}
