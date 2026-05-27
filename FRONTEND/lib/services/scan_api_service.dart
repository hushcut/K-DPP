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
    this.endpoint = const String.fromEnvironment(
      'SCAN_API_ENDPOINT',
      defaultValue: 'http://10.0.2.2:8000/api/scan',
    ),
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
      throw ScanApiException(
        '\uC11C\uBC84 \uC624\uB958(${response.statusCode})\uAC00 \uBC1C\uC0DD\uD588\uC2B5\uB2C8\uB2E4.',
      );
    }

    dynamic decodedData;
    try {
      decodedData = json.decode(rawBody);
    } catch (_) {
      throw const ScanApiException(
        '\uC751\uB2F5 JSON \uD30C\uC2F1\uC5D0 \uC2E4\uD328\uD588\uC2B5\uB2C8\uB2E4.',
      );
    }

    if (decodedData is! Map<String, dynamic>) {
      throw const ScanApiException(
        '\uC751\uB2F5 \uD615\uC2DD\uC774 \uC62C\uBC14\uB974\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.',
      );
    }

    final status = decodedData['status'];
    if (status != 'success') {
      final message =
          decodedData['message']?.toString() ??
          '\uBD84\uC11D \uC2E4\uD328 \uC751\uB2F5\uC785\uB2C8\uB2E4.';
      throw ScanApiException(message);
    }

    try {
      return ScanResult.fromJson(decodedData);
    } on FormatException catch (e) {
      throw ScanApiException(e.message);
    }
  }
}
