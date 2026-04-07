import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../models/scan_result.dart';

class ScanApiException implements Exception {
  final String message;

  const ScanApiException(this.message);

  @override
  String toString() => message;
}

class ScanApiService {
  final String endpoint;

  const ScanApiService({
    this.endpoint =
    'https://nonmimetically-unplacid-zachery.ngrok-free.dev/api/scan',
  });

  Future<ScanResult> scanLabel({required File imageFile}) async {
    final request = http.MultipartRequest('POST', Uri.parse(endpoint))
      ..headers.addAll({
        'ngrok-skip-browser-warning': 'true',
      })
      ..files.add(
        await http.MultipartFile.fromPath('image', imageFile.path),
      );

    final streamedResponse = await request.send();
    final response = await http.Response.fromStream(streamedResponse);
    final rawBody = utf8.decode(response.bodyBytes);

    if (response.statusCode != 200) {
      throw ScanApiException('서버 오류(${response.statusCode})가 발생했습니다.');
    }

    dynamic decodedData;
    try {
      decodedData = json.decode(rawBody);
    } catch (_) {
      throw const ScanApiException('응답 JSON 파싱에 실패했습니다.');
    }

    if (decodedData is! Map<String, dynamic>) {
      throw const ScanApiException('응답 형식이 올바르지 않습니다.');
    }

    final status = decodedData['status'];
    if (status != 'success') {
      final message = decodedData['message']?.toString() ?? '분석 실패 응답입니다.';
      throw ScanApiException(message);
    }

    try {
      return ScanResult.fromJson(decodedData);
    } on FormatException catch (e) {
      throw ScanApiException(e.message);
    }
  }
}