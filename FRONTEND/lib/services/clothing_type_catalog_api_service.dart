import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../config/api_environment.dart';
import '../models/clothing_type_option.dart';
import 'api_http.dart';

/// 서버 `GET /clothing-types`에서 의류 종류별 무게 범위를 받아 옵션 목록으로 바꾼다.
class ClothingTypeCatalogApiService {
  ClothingTypeCatalogApiService({
    String? endpoint,
    this.requestHeaders = const {
      'Accept': 'application/json',
      'ngrok-skip-browser-warning': 'true',
    },
    this.requestTimeout = const Duration(seconds: 10),
    this.client,
  }) : endpoint = endpoint ?? ApiEnvironment.clothingTypesEndpoint;

  final String endpoint;
  final Map<String, String> requestHeaders;
  final Duration requestTimeout;
  final http.Client? client;

  /// 검증을 통과한 항목만 서버 순서대로 돌려준다.
  ///
  /// 요청이 실패했거나, 형식이 다르거나, 쓸 수 있는 항목이 하나도 없으면 예외를 던진다 —
  /// 부르는 쪽은 그때 앱 내장 표를 그대로 쓴다. 일부 항목만 이상하면 그 항목만 뺀다.
  Future<List<ClothingTypeOption>> fetchClothingTypes() async {
    final response = await runJsonApiRequest(
      method: 'GET',
      uri: Uri.parse(endpoint),
      headers: requestHeaders,
      timeout: requestTimeout,
      client: client,
    );

    if (!response.isSuccess) {
      throw HttpException('의류 무게표 요청에 실패했습니다. (${response.statusCode})');
    }

    final decoded = jsonDecode(response.body);
    final rawItems = decoded is Map ? decoded['items'] : null;
    if (rawItems is! List) {
      throw const FormatException('의류 무게표에 items 목록이 없습니다.');
    }

    final options = rawItems
        .whereType<Map>()
        .map((item) => ClothingTypeOption.fromServerJson(
              Map<String, dynamic>.from(item),
            ))
        .whereType<ClothingTypeOption>()
        .toList(growable: false);

    if (options.isEmpty) {
      throw const FormatException('의류 무게표에 쓸 수 있는 항목이 없습니다.');
    }

    return options;
  }
}
