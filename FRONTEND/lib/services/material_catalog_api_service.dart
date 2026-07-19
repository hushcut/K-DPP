import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../config/api_environment.dart';

/// 서버 소재 카탈로그의 식별자, 한·영 이름, 검색 별칭을 표현한다.
class MaterialCatalogItem {
  const MaterialCatalogItem({
    required this.id,
    required this.nameKo,
    required this.nameEn,
    required this.aliases,
  });

  final int id;
  final String nameKo;
  final String nameEn;
  final List<String> aliases;

  String get label => '$nameKo ($nameEn)';

  /// 한글명, 영문명, 별칭 중 검색어를 포함하는 항목인지 확인한다.
  bool matches(String query) {
    final normalizedQuery = query.trim().toLowerCase();
    if (normalizedQuery.isEmpty) return true;

    return nameKo.toLowerCase().contains(normalizedQuery) ||
        nameEn.toLowerCase().contains(normalizedQuery) ||
        aliases.any((alias) => alias.toLowerCase().contains(normalizedQuery));
  }

  /// 필수 필드가 누락되거나 ID·이름 형식이 잘못된 응답은 [FormatException]으로 거부한다.
  factory MaterialCatalogItem.fromJson(Map<String, dynamic> json) {
    final id = _parseInt(json['id']);
    final nameKo = json['name_ko']?.toString().trim() ?? '';
    final nameEn = json['name_en']?.toString().trim() ?? '';
    final rawAliases = json['aliases'];
    final aliases = rawAliases is List
        ? rawAliases
              .map((alias) => alias.toString().trim())
              .where((alias) => alias.isNotEmpty)
              .toList()
        : const <String>[];

    if (id == null || nameKo.isEmpty || nameEn.isEmpty) {
      throw const FormatException('소재 기준표 응답이 올바르지 않습니다.');
    }

    return MaterialCatalogItem(
      id: id,
      nameKo: nameKo,
      nameEn: nameEn,
      aliases: aliases,
    );
  }

  static int? _parseInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '');
  }
}

/// 서버에서 소재 기준 목록을 가져와 검색 가능한 카탈로그 항목으로 변환한다.
class MaterialCatalogApiService {
  MaterialCatalogApiService({
    String? endpoint,
    this.requestHeaders = const {
      'Accept': 'application/json',
      'ngrok-skip-browser-warning': 'true',
    },
    this.requestTimeout = const Duration(seconds: 10),
    this.client,
  }) : endpoint = endpoint ?? ApiEnvironment.materialsEndpoint;

  final String endpoint;
  final Map<String, String> requestHeaders;
  final Duration requestTimeout;
  final http.Client? client;

  /// 목록 JSON만 허용하며, 서비스가 직접 만든 HTTP 클라이언트는 요청 후 닫는다.
  Future<List<MaterialCatalogItem>> fetchMaterials() async {
    final activeClient = client ?? http.Client();
    final shouldCloseClient = client == null;

    try {
      final response = await activeClient
          .get(Uri.parse(endpoint), headers: requestHeaders)
          .timeout(requestTimeout);

      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw HttpException('소재 기준표 요청에 실패했습니다. (${response.statusCode})');
      }

      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is! List) {
        throw const FormatException('소재 기준표가 목록 형식이 아닙니다.');
      }

      return decoded
          .whereType<Map>()
          .map(
            (item) =>
                MaterialCatalogItem.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(growable: false);
    } finally {
      if (shouldCloseClient) {
        activeClient.close();
      }
    }
  }
}
