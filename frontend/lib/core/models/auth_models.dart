/// Identity, company and reference models shared across the client.
class KayanUser {
  const KayanUser({
    required this.id,
    required this.email,
    required this.fullName,
    this.fullNameAr,
    this.jobTitle,
    this.language,
    this.avatarUrl,
    this.isSuperuser = false,
    this.mustChangePassword = false,
  });

  final String id;
  final String email;
  final String fullName;
  final String? fullNameAr;
  final String? jobTitle;
  final String? language;
  final String? avatarUrl;
  final bool isSuperuser;
  final bool mustChangePassword;

  String get displayName => fullNameAr?.isNotEmpty == true ? fullNameAr! : fullName;

  String get initials {
    final List<String> parts = displayName.trim().split(RegExp(r'\s+'));
    if (parts.isEmpty || parts.first.isEmpty) return '?';
    if (parts.length == 1) return parts.first.characters_first;
    return '${parts.first.characters_first}${parts.last.characters_first}';
  }

  factory KayanUser.fromJson(Map<String, dynamic> json) => KayanUser(
        id: '${json['id']}',
        email: '${json['email'] ?? ''}',
        fullName: '${json['full_name'] ?? json['email'] ?? ''}',
        fullNameAr: json['full_name_ar']?.toString(),
        jobTitle: json['job_title']?.toString(),
        language: json['language']?.toString(),
        avatarUrl: json['avatar_url']?.toString(),
        isSuperuser: json['is_superuser'] == true,
        mustChangePassword: json['must_change_password'] == true,
      );
}

extension on String {
  /// First character, used for avatars without pulling in a characters import.
  String get characters_first => isEmpty ? '?' : substring(0, 1).toUpperCase();
}

class CompanyRef {
  const CompanyRef({
    required this.id,
    required this.code,
    required this.name,
    this.nameAr,
    this.baseCurrencyCode,
    this.logoUrl,
  });

  final String id;
  final String code;
  final String name;
  final String? nameAr;
  final String? baseCurrencyCode;
  final String? logoUrl;

  String get displayName => nameAr?.isNotEmpty == true ? nameAr! : name;

  factory CompanyRef.fromJson(Map<String, dynamic> json) => CompanyRef(
        id: '${json['id']}',
        code: '${json['code'] ?? ''}',
        name: '${json['name'] ?? ''}',
        nameAr: json['name_ar']?.toString(),
        baseCurrencyCode: json['base_currency_code']?.toString(),
        logoUrl: json['logo_url']?.toString(),
      );
}

class LookupRef {
  const LookupRef({required this.id, required this.code, required this.name});

  final String id;
  final String code;
  final String name;

  factory LookupRef.fromJson(Map<String, dynamic> json) => LookupRef(
        id: '${json['id']}',
        code: '${json['code'] ?? ''}',
        name: '${json['name'] ?? json['full_name'] ?? ''}',
      );
}

class RoleRef {
  const RoleRef({required this.code, required this.name, this.nameAr, this.level, this.dataScope});

  final String code;
  final String name;
  final String? nameAr;
  final int? level;
  final String? dataScope;

  factory RoleRef.fromJson(Map<String, dynamic> json) => RoleRef(
        code: '${json['code']}',
        name: '${json['name'] ?? json['code']}',
        nameAr: json['name_ar']?.toString(),
        level: json['level'] is int ? json['level'] as int : int.tryParse('${json['level']}'),
        dataScope: json['data_scope']?.toString(),
      );
}

/// Everything the UI needs after sign-in.
class AuthState {
  const AuthState({
    required this.accessToken,
    required this.refreshToken,
    required this.companyId,
    required this.permissions,
    this.sessionId,
    this.user,
    this.company,
    this.companies = const <CompanyRef>[],
    this.branches = const <LookupRef>[],
    this.warehouses = const <LookupRef>[],
    this.roles = const <RoleRef>[],
    this.modules = const <String>[],
    this.dataScope,
    this.mustChangePassword = false,
  });

  final String accessToken;
  final String refreshToken;
  final String companyId;
  final String? sessionId;
  final Set<String> permissions;
  final KayanUser? user;
  final CompanyRef? company;
  final List<CompanyRef> companies;
  final List<LookupRef> branches;
  final List<LookupRef> warehouses;
  final List<RoleRef> roles;
  final List<String> modules;
  final String? dataScope;
  final bool mustChangePassword;

  bool get isSuperuser => user?.isSuperuser ?? false;

  /// ``*`` means "superuser: every permission".
  bool can(String permission) => isSuperuser || permissions.contains('*') || permissions.contains(permission);

  bool canAny(Iterable<String> codes) => codes.any(can);

  bool hasModule(String code) => modules.isEmpty || modules.contains(code);

  const AuthState.anonymous()
      : accessToken = '',
        refreshToken = '',
        companyId = '',
        sessionId = null,
        permissions = const <String>{},
        user = null,
        company = null,
        companies = const <CompanyRef>[],
        branches = const <LookupRef>[],
        warehouses = const <LookupRef>[],
        roles = const <RoleRef>[],
        modules = const <String>[],
        dataScope = null,
        mustChangePassword = false;

  bool get isAuthenticated => accessToken.isNotEmpty;

  AuthState copyWith({
    String? accessToken,
    String? refreshToken,
    String? companyId,
    String? sessionId,
    Set<String>? permissions,
    KayanUser? user,
    CompanyRef? company,
    List<CompanyRef>? companies,
    List<LookupRef>? branches,
    List<LookupRef>? warehouses,
    List<RoleRef>? roles,
    List<String>? modules,
    String? dataScope,
    bool? mustChangePassword,
  }) {
    return AuthState(
      accessToken: accessToken ?? this.accessToken,
      refreshToken: refreshToken ?? this.refreshToken,
      companyId: companyId ?? this.companyId,
      sessionId: sessionId ?? this.sessionId,
      permissions: permissions ?? this.permissions,
      user: user ?? this.user,
      company: company ?? this.company,
      companies: companies ?? this.companies,
      branches: branches ?? this.branches,
      warehouses: warehouses ?? this.warehouses,
      roles: roles ?? this.roles,
      modules: modules ?? this.modules,
      dataScope: dataScope ?? this.dataScope,
      mustChangePassword: mustChangePassword ?? this.mustChangePassword,
    );
  }

  factory AuthState.fromLogin(Map<String, dynamic> json, {KayanUser? user}) {
    final Object? rawPermissions = json['permissions'];
    return AuthState(
      accessToken: '${json['access_token'] ?? ''}',
      refreshToken: '${json['refresh_token'] ?? ''}',
      companyId: '${json['company_id'] ?? ''}',
      sessionId: json['session_id']?.toString(),
      permissions: rawPermissions is List
          ? rawPermissions.map<String>((Object? value) => '$value').toSet()
          : <String>{},
      user: user,
      mustChangePassword: json['must_change_password'] == true,
    );
  }

  factory AuthState.fromProfile(Map<String, dynamic> json, {required AuthState previous}) {
    final Object? rawPermissions = json['permissions'];
    final Object? rawCompanies = json['companies'];
    final Object? rawBranches = json['branches'];
    final Object? rawWarehouses = json['warehouses'];
    final Object? rawRoles = json['roles'];
    final Object? rawModules = json['modules'];
    final Object? rawCompany = json['company'];
    return previous.copyWith(
      permissions: rawPermissions is List
          ? rawPermissions.map<String>((Object? value) => '$value').toSet()
          : previous.permissions,
      user: json['user'] is Map<String, dynamic>
          ? KayanUser.fromJson(json['user'] as Map<String, dynamic>)
          : previous.user,
      company: rawCompany is Map<String, dynamic> ? CompanyRef.fromJson(rawCompany) : previous.company,
      companies: rawCompanies is List
          ? rawCompanies
              .whereType<Map<String, dynamic>>()
              .map<CompanyRef>(CompanyRef.fromJson)
              .toList(growable: false)
          : previous.companies,
      branches: rawBranches is List
          ? rawBranches
              .whereType<Map<String, dynamic>>()
              .map<LookupRef>(LookupRef.fromJson)
              .toList(growable: false)
          : previous.branches,
      warehouses: rawWarehouses is List
          ? rawWarehouses
              .whereType<Map<String, dynamic>>()
              .map<LookupRef>(LookupRef.fromJson)
              .toList(growable: false)
          : previous.warehouses,
      roles: rawRoles is List
          ? rawRoles.whereType<Map<String, dynamic>>().map<RoleRef>(RoleRef.fromJson).toList(growable: false)
          : previous.roles,
      modules: rawModules is List ? rawModules.map<String>((Object? value) => '$value').toList() : previous.modules,
      dataScope: json['data_scope']?.toString() ?? previous.dataScope,
      sessionId: json['session_id']?.toString() ?? previous.sessionId,
    );
  }
}

/// A downloadable picture from the download-ticket endpoint.
class DownloadTicket {
  const DownloadTicket({required this.url, required this.fileName, required this.expiresAt, required this.fileFormat});

  final String url;
  final String fileName;
  final String expiresAt;
  final String fileFormat;

  factory DownloadTicket.fromJson(Map<String, dynamic> json) => DownloadTicket(
        url: '${json['url'] ?? ''}',
        fileName: '${json['file_name'] ?? 'export'}',
        expiresAt: '${json['expires_at'] ?? ''}',
        fileFormat: '${json['file_format'] ?? 'csv'}',
      );
}
