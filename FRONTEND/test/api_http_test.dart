import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:k_dpp/services/api_http.dart';

void main() {
  late Directory tempDirectory;
  late File imageFile;

  setUp(() async {
    tempDirectory = await Directory.systemTemp.createTemp('k_dpp_api_http_test_');
    imageFile = File('${tempDirectory.path}/label.jpg');
    await imageFile.writeAsBytes(const [0xFF, 0xD8, 0xFF, 0xD9]);
  });

  tearDown(() async {
    if (await tempDirectory.exists()) {
      await tempDirectory.delete(recursive: true);
    }
  });

  /// 헤더와 본문 도착을 각각 지연시키는 스트리밍 클라이언트입니다.
  MockClient delayedClient({
    required Duration headerDelay,
    required Duration bodyDelay,
  }) {
    return MockClient.streaming((request, bodyStream) async {
      await Future<void>.delayed(headerDelay);

      final body = Stream<List<int>>.fromFuture(
        Future<List<int>>.delayed(bodyDelay, () => utf8.encode('{"ok":true}')),
      );

      return http.StreamedResponse(body, 200);
    });
  }

  group('runImageUploadRequest 타임아웃', () {
    test('헤더와 본문 대기를 합쳐 timeout을 한 번만 적용한다', () async {
      // 각 단계에 따로 timeout을 걸면 두 단계 모두 상한 미만이라 성공해 버리고,
      // 실제 상한이 timeout의 두 배가 된다. 합쳐서 재면 초과이므로 시간 초과여야 한다.
      final client = delayedClient(
        headerDelay: const Duration(milliseconds: 150),
        bodyDelay: const Duration(milliseconds: 150),
      );

      await expectLater(
        runImageUploadRequest(
          uri: Uri.parse('https://example.test/api/scan'),
          headers: const {},
          timeout: const Duration(milliseconds: 200),
          imageFile: imageFile,
          fieldName: 'image',
          client: client,
        ),
        throwsA(
          isA<ApiTransportException>().having(
            (error) => error.type,
            'type',
            ApiTransportErrorType.timeout,
          ),
        ),
      );
    });

    test('상한 안에 끝나면 응답 본문을 그대로 돌려준다', () async {
      final client = delayedClient(
        headerDelay: const Duration(milliseconds: 20),
        bodyDelay: const Duration(milliseconds: 20),
      );

      final response = await runImageUploadRequest(
        uri: Uri.parse('https://example.test/api/scan'),
        headers: const {},
        timeout: const Duration(milliseconds: 500),
        imageFile: imageFile,
        fieldName: 'image',
        client: client,
      );

      expect(response.statusCode, 200);
      expect(response.body, '{"ok":true}');
    });
  });
}
