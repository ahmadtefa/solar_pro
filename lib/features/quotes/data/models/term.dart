class Term {
  final int? id;
  final int quoteId;
  final String text;
  final int orderIndex;

  const Term({
    this.id,
    required this.quoteId,
    required this.text,
    this.orderIndex = 0,
  });

  factory Term.create({
    required int quoteId,
    required String text,
    int orderIndex = 0,
  }) {
    return Term(
      quoteId: quoteId,
      text: text,
      orderIndex: orderIndex,
    );
  }

  Term copyWith({
    int? id,
    int? quoteId,
    String? text,
    int? orderIndex,
  }) {
    return Term(
      id: id ?? this.id,
      quoteId: quoteId ?? this.quoteId,
      text: text ?? this.text,
      orderIndex: orderIndex ?? this.orderIndex,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      if (id != null) 'id': id,
      'quoteId': quoteId,
      'text': text,
      'orderIndex': orderIndex,
    };
  }

  factory Term.fromMap(Map<String, dynamic> map) {
    return Term(
      id: map['id'] as int?,
      quoteId: map['quoteId'] as int,
      text: map['text'] as String,
      orderIndex: map['orderIndex'] as int? ?? 0,
    );
  }

  Map<String, dynamic> toJson() => toMap();

  factory Term.fromJson(Map<String, dynamic> json) => Term.fromMap(json);

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Term &&
          runtimeType == other.runtimeType &&
          id == other.id &&
          quoteId == other.quoteId &&
          text == other.text &&
          orderIndex == other.orderIndex;

  @override
  int get hashCode {
    return Object.hash(id, quoteId, text, orderIndex);
  }

  @override
  String toString() {
    return 'Term(id: $id, quoteId: $quoteId, text: $text, orderIndex: $orderIndex)';
  }
}
