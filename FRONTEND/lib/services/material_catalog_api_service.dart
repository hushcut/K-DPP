import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../config/api_environment.dart';

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

  bool matches(String query) {
    final normalizedQuery = query.trim().toLowerCase();
    if (normalizedQuery.isEmpty) return true;

    return nameKo.toLowerCase().contains(normalizedQuery) ||
        nameEn.toLowerCase().contains(normalizedQuery) ||
        aliases.any((alias) => alias.toLowerCase().contains(normalizedQuery));
  }

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
