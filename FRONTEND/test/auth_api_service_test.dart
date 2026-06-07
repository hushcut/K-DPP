import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:k_dpp/services/auth_api_service.dart';

void main() {
  group('AuthApiService configuration', () {
    test('uses the Android emulator backend URL by default', () {
      final service = AuthApiService();

      expect(service.baseUrl, 'http://10.0.2.2:8000');
    });

    test('normalizes a trailing slash in the injected backend URL', () async {
      late http.Request capturedRequest;
      final client = MockClient((request) async {
        capturedRequest = request;

        return http.Response(
          jsonEncode({
            'status': 'success',
            'user': {
              'id': 1,
              'email': 'honggildong@example.com',
              'nickname': '홍길동',
            },
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      });
      final service = AuthApiService(
        baseUrl: 'https://example.ngrok-free.app/',
        client: client,
      );

      try {
        await service.signup(
          nickname: '홍길동',
          email: 'honggildong@example.com',
          password: 'password123',
        );

        expect(
          capturedRequest.url,
          Uri.parse('https://example.ngrok-free.app/auth/signup'),
        );
      } finally {
        client.close();
      }
    });
  });

  group('FastAPI auth contract', () {
    test('sends the login request and parses the user and token', () async {
      late http.Request capturedRequest;
      final client = MockClient((request) async {
        capturedRequest = request;

        return http.Response(
          jsonEncode({
            'status': 'success',
            'message': '로그인되었습니다.',
            'user': {
              'id': 7,
              'email': 'honggildong@example.com',
              'nickname': '홍길동',
            },
            'access_token': 'temporary-token',
            'token_type': 'bearer',
            'expires_in': 2592000,
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      });
      final service = AuthApiService(client: client);

      try {
        final result = await service.login(
          email: ' honggildong@example.com ',
          password: 'password123',
        );
        final requestBody =
            jsonDecode(capturedRequest.body) as Map<String, dynamic>;

        expect(capturedRequest.method, 'POST');
        expect(
          capturedRequest.url,
          Uri.parse('http://10.0.2.2:8000/auth/login'),
        );
        expect(capturedRequest.headers['content-type'], 'application/json');
        expect(capturedRequest.headers['accept'], 'application/json');
        expect(capturedRequest.headers['ngrok-skip-browser-warning'], 'true');
        expect(requestBody, {
          'email': 'honggildong@example.com',
          'password': 'password123',
        });
        expect(result.user.id, 7);
        expect(result.user.email, 'honggildong@example.com');
        expect(result.user.nickname, '홍길동');
        expect(result.accessToken, 'temporary-token');
        expect(result.tokenType, 'bearer');
        expect(result.expiresInSeconds, 2592000);
      } finally {
        client.close();
      }
    });

    test(
      'sends the signup request and parses a response without token',
      () async {
        late http.Request capturedRequest;
        final client = MockClient((request) async {
          capturedRequest = request;

          return http.Response(
            jsonEncode({
              'status': 'success',
              'message': '회원가입이 완료되었습니다.',
              'user': {
                'id': 8,
                'email': 'honggildong@example.com',
                'nickname': '홍길동',
              },
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        });
        final service = AuthApiService(client: client);

        try {
          final result = await service.signup(
            nickname: ' 홍길동 ',
            email: ' honggildong@example.com ',
            password: 'password123',
          );
          final requestBody =
              jsonDecode(capturedRequest.body) as Map<String, dynamic>;

          expect(
            capturedRequest.url,
            Uri.parse('http://10.0.2.2:8000/auth/signup'),
          );
          expect(requestBody, {
            'nickname': '홍길동',
            'email': 'honggildong@example.com',
            'password': 'password123',
          });
          expect(result.user.id, 8);
          expect(result.accessToken, isNull);
          expect(result.expiresInSeconds, isNull);
        } finally {
          client.close();
        }
      },
    );

    test('maps an invalid login response to unauthorized', () async {
      final client = MockClient(
        (_) async => http.Response(
          jsonEncode({'detail': '이메일 또는 비밀번호가 올바르지 않습니다.'}),
          401,
          headers: {'content-type': 'application/json; charset=utf-8'},
        ),
      );
      final service = AuthApiService(client: client);

      try {
        await expectLater(
          service.login(
            email: 'honggildong@example.com',
            password: 'wrong-password',
          ),
          throwsA(
            isA<AuthApiException>()
                .having(
                  (error) => error.type,
                  'type',
                  AuthApiErrorType.unauthorized,
                )
                .having((error) => error.statusCode, 'statusCode', 401)
                .having(
                  (error) => error.userMessage,
                  'userMessage',
                  '이메일 또는 비밀번호가 올바르지 않습니다.',
                ),
          ),
        );
      } finally {
        client.close();
      }
    });

    test('maps a duplicate signup response to conflict', () async {
      final client = MockClient(
        (_) async => http.Response(
          jsonEncode({'detail': '이미 가입된 이메일입니다.'}),
          409,
          headers: {'content-type': 'application/json; charset=utf-8'},
        ),
      );
      final service = AuthApiService(client: client);

      try {
        await expectLater(
          service.signup(
            nickname: '홍길동',
            email: 'honggildong@example.com',
            password: 'password123',
          ),
          throwsA(
            isA<AuthApiException>()
                .having(
                  (error) => error.type,
                  'type',
                  AuthApiErrorType.conflict,
                )
                .having((error) => error.statusCode, 'statusCode', 409)
                .having(
                  (error) => error.userMessage,
                  'userMessage',
                  '이미 가입된 이메일입니다.',
                ),
          ),
        );
      } finally {
        client.close();
      }
    });

    test('rejects a success response without valid user data', () async {
      final client = MockClient(
        (_) async => http.Response(
          jsonEncode({'status': 'success', 'user': null}),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        ),
      );
      final service = AuthApiService(client: client);

      try {
        await expectLater(
          service.login(
            email: 'honggildong@example.com',
            password: 'password123',
          ),
          throwsA(
            isA<AuthApiException>().having(
              (error) => error.type,
              'type',
              AuthApiErrorType.invalidResponse,
            ),
          ),
        );
      } finally {
        client.close();
      }
    });

    test('rejects a login response without session expiry', () async {
      final client = MockClient(
        (_) async => http.Response(
          jsonEncode({
            'status': 'success',
            'user': {
              'id': 7,
              'email': 'honggildong@example.com',
              'nickname': '홍길동',
            },
            'access_token': 'token-without-expiry',
            'token_type': 'bearer',
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        ),
      );
      final service = AuthApiService(client: client);

      try {
        await expectLater(
          service.login(
            email: 'honggildong@example.com',
            password: 'password123',
          ),
          throwsA(
            isA<AuthApiException>().having(
              (error) => error.type,
              'type',
              AuthApiErrorType.invalidResponse,
            ),
          ),
        );
      } finally {
        client.close();
      }
    });

    test('sends the bearer token when logging out', () async {
      late http.Request capturedRequest;
      final client = MockClient((request) async {
        capturedRequest = request;

        return http.Response(
          jsonEncode({'status': 'success', 'message': '로그아웃되었습니다.'}),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      });
      final service = AuthApiService(client: client);

      try {
        await service.logout(accessToken: 'saved-access-token');

        expect(
          capturedRequest.url,
          Uri.parse('http://10.0.2.2:8000/auth/logout'),
        );
        expect(
          capturedRequest.headers['authorization'],
          'Bearer saved-access-token',
        );
      } finally {
        client.close();
      }
    });

    test('validates a stored token and parses the current user', () async {
      late http.Request capturedRequest;
      final client = MockClient((request) async {
        capturedRequest = request;

        return http.Response(
          jsonEncode({
            'status': 'success',
            'user': {
              'id': 7,
              'email': 'honggildong@example.com',
              'nickname': '홍길동',
            },
            'history': [],
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      });
      final service = AuthApiService(client: client);

      try {
        final user = await service.validateSession(
          accessToken: 'saved-access-token',
        );

        expect(
          capturedRequest.url,
          Uri.parse('http://10.0.2.2:8000/me/history'),
        );
        expect(capturedRequest.method, 'GET');
        expect(
          capturedRequest.headers['authorization'],
          'Bearer saved-access-token',
        );
        expect(user.id, 7);
        expect(user.email, 'honggildong@example.com');
        expect(user.nickname, '홍길동');
      } finally {
        client.close();
      }
    });

    test('maps a revoked stored token to unauthorized', () async {
      final client = MockClient(
        (_) async => http.Response(
          jsonEncode({'status': 'error', 'message': '로그인이 필요합니다.'}),
          401,
          headers: {'content-type': 'application/json; charset=utf-8'},
        ),
      );
      final service = AuthApiService(client: client);

      try {
        await expectLater(
          service.validateSession(accessToken: 'revoked-token'),
          throwsA(
            isA<AuthApiException>()
                .having(
                  (error) => error.type,
                  'type',
                  AuthApiErrorType.unauthorized,
                )
                .having((error) => error.statusCode, 'statusCode', 401),
          ),
        );
      } finally {
        client.close();
      }
    });

    test('parses the current user and server history in one request', () async {
      final client = MockClient(
        (_) async => http.Response(
          jsonEncode({
            'status': 'success',
            'user': {
              'id': 7,
              'email': 'honggildong@example.com',
              'nickname': '홍길동',
            },
            'history': [
              {
                'id': 13,
                'user_id': 7,
                'materials': {'cotton': 100},
                'carbon_footprint': 1.46,
                'carbon_footprint_min': 0.83,
                'carbon_footprint_max': 2.08,
                'min_weight_grams': 100,
                'max_weight_grams': 250,
                'created_at': '2026-06-04T12:00:00',
              },
            ],
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        ),
      );
      final service = AuthApiService(client: client);

      try {
        final snapshot = await service.fetchSessionSnapshot(
          accessToken: 'saved-access-token',
        );

        expect(snapshot.user.nickname, '홍길동');
        expect(snapshot.history.single.id, 13);
        expect(snapshot.history.single.carbonFootprint, 1.46);
        expect(snapshot.history.single.maxWeightGram, 250);
      } finally {
        client.close();
      }
    });
  });
}
