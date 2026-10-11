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
          code: '123456',
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
            code: ' 123456 ',
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
            'code': '123456',
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
            code: '123456',
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

  group('user object (login_methods)', () {
    Future<AuthUser> parseSessionUser(Map<String, dynamic> user) async {
      final client = MockClient(
        (_) async => http.Response(
          jsonEncode({'status': 'success', 'user': user, 'history': []}),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        ),
      );
      final service = AuthApiService(client: client);

      try {
        final snapshot = await service.fetchSessionSnapshot(
          accessToken: 'saved-access-token',
        );
        return snapshot.user;
      } finally {
        client.close();
      }
    }

    test('accepts a kakao account whose email is null', () async {
      final user = await parseSessionUser({
        'id': 7,
        'email': null,
        'nickname': '카카오 사용자',
        'login_methods': ['kakao'],
      });

      expect(user.id, 7);
      expect(user.email, isNull);
      expect(user.nickname, '카카오 사용자');
      expect(user.loginMethods, ['kakao']);
      expect(user.hasPasswordLogin, isFalse);
    });

    test('treats a user without login_methods as a password account', () async {
      // login_methods 가 생기기 전 서버의 응답입니다.
      final user = await parseSessionUser({
        'id': 1,
        'email': 'honggildong@example.com',
        'nickname': '홍길동',
      });

      expect(user.loginMethods, ['password']);
      expect(user.hasPasswordLogin, isTrue);
    });

    test('keeps unknown login methods but skips non-strings', () async {
      final user = await parseSessionUser({
        'id': 2,
        'email': 'honggildong@example.com',
        'nickname': '홍길동',
        'login_methods': ['google', 3, 'password'],
      });

      expect(user.loginMethods, ['google', 'password']);
      expect(user.hasPasswordLogin, isTrue);
    });

    test('still rejects a user without an id or a nickname', () async {
      for (final user in <Map<String, dynamic>>[
        {
          'email': null,
          'nickname': '카카오 사용자',
          'login_methods': ['kakao'],
        },
        {
          'id': 7,
          'email': null,
          'nickname': ' ',
          'login_methods': ['kakao'],
        },
      ]) {
        await expectLater(
          parseSessionUser(user),
          throwsA(
            isA<AuthApiException>().having(
              (error) => error.type,
              'type',
              AuthApiErrorType.invalidResponse,
            ),
          ),
        );
      }
    });
  });

  group('kakao login (POST /auth/kakao)', () {
    http.Response jsonResponse(Map<String, dynamic> body, int statusCode) {
      return http.Response(
        jsonEncode(body),
        statusCode,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    }

    Map<String, dynamic> kakaoSuccess({required bool isNewUser}) {
      return {
        'status': 'success',
        'message': isNewUser ? '카카오 계정으로 가입했습니다.' : '로그인되었습니다.',
        'user': {
          'id': 7,
          'email': null,
          'nickname': '카카오 사용자',
          'login_methods': ['kakao'],
        },
        'access_token': 'server-token',
        'token_type': 'bearer',
        'expires_in': 2592000,
        'is_new_user': isNewUser,
      };
    }

    /// 서버(`http_exception_handler`)가 카카오 오류에 보내는 봉투입니다.
    http.Response kakaoError(int statusCode, String errorCode, String message) {
      return jsonResponse({
        'status': 'error',
        'error_code': errorCode,
        'message': message,
        'detail': {'message': message, 'error_code': errorCode},
      }, statusCode);
    }

    test('sends only the kakao token first and parses a new account', () async {
      late http.Request captured;
      final client = MockClient((request) async {
        captured = request;
        return jsonResponse(kakaoSuccess(isNewUser: true), 200);
      });
      final service = AuthApiService(
        baseUrl: 'https://example.test',
        client: client,
      );

      final result = await service.kakaoLogin(accessToken: 'kakao-token');

      expect(captured.method, 'POST');
      expect(captured.url.path, '/auth/kakao');
      // 첫 요청에 nickname 칸이 있으면 서버가 카카오 사용자 정보를 조회하지 않는다(DECISIONS 163).
      expect(jsonDecode(captured.body), {'access_token': 'kakao-token'});
      expect(captured.headers.containsKey('Authorization'), isFalse);
      expect(result.isNewUser, isTrue);
      expect(result.accessToken, 'server-token');
      expect(result.expiresInSeconds, 2592000);
      expect(result.user.id, 7);
      expect(result.user.email, isNull);
      expect(result.user.loginMethods, ['kakao']);
      expect(result.user.hasPasswordLogin, isFalse);
    });

    test(
      'sends the trimmed nickname with the same kakao token when asked',
      () async {
        late http.Request captured;
        final service = AuthApiService(
          baseUrl: 'https://example.test',
          client: MockClient((request) async {
            captured = request;
            return jsonResponse(kakaoSuccess(isNewUser: false), 200);
          }),
        );

        final result = await service.kakaoLogin(
          accessToken: 'kakao-token',
          nickname: '  새 닉네임 ',
        );

        expect(jsonDecode(captured.body), {
          'access_token': 'kakao-token',
          'nickname': '새 닉네임',
        });
        expect(result.isNewUser, isFalse);
      },
    );

    test(
      'treats a login response without is_new_user as an existing account',
      () async {
        final service = AuthApiService(
          client: MockClient(
            (_) async => jsonResponse({
              'status': 'success',
              'user': {
                'id': 1,
                'email': 'honggildong@example.com',
                'nickname': '홍길동',
              },
              'access_token': 'server-token',
              'expires_in': 3600,
            }, 200),
          ),
        );

        final result = await service.login(
          email: 'honggildong@example.com',
          password: 'password123',
        );

        expect(result.isNewUser, isFalse);
      },
    );

    test(
      'keeps SOCIAL_NICKNAME_REQUIRED so the screen can ask for a nickname',
      () async {
        final service = AuthApiService(
          client: MockClient(
            (_) async => kakaoError(
              400,
              'SOCIAL_NICKNAME_REQUIRED',
              '사용할 닉네임을 입력해 주세요.',
            ),
          ),
        );

        await expectLater(
          service.kakaoLogin(accessToken: 'kakao-token'),
          throwsA(
            isA<AuthApiException>()
                .having(
                  (error) => error.type,
                  'type',
                  AuthApiErrorType.badRequest,
                )
                .having(
                  (error) => error.errorCode,
                  'errorCode',
                  AuthErrorCode.socialNicknameRequired,
                ),
          ),
        );
      },
    );

    test(
      'maps kakao error codes to app messages, not email-login wording',
      () async {
        final cases = <(int, String, String, String)>[
          (
            401,
            'SOCIAL_TOKEN_INVALID',
            '카카오 로그인을 확인하지 못했습니다. 카카오 로그인을 다시 해 주세요.',
            '카카오 로그인을 확인하지 못했어요. 카카오 로그인부터 다시 해 주세요.',
          ),
          (
            400,
            'SOCIAL_ACCOUNT_MISMATCH',
            '이 계정에 연결된 카카오 계정이 아닙니다. 가입한 카카오 계정으로 다시 로그인해 주세요.',
            '가입한 카카오 계정이 아니에요. 가입한 카카오 계정으로 다시 확인해 주세요.',
          ),
          (
            502,
            'SOCIAL_PROVIDER_UNAVAILABLE',
            '카카오 서버가 응답하지 않습니다. 잠시 후 다시 시도해 주세요.',
            '카카오가 응답하지 않아요. 잠시 후 다시 시도해 주세요.',
          ),
          (
            503,
            'SOCIAL_LOGIN_UNAVAILABLE',
            '이 서버에서는 카카오 로그인을 쓸 수 없습니다.',
            '지금은 카카오 로그인을 쓸 수 없어요.',
          ),
        ];

        for (final (statusCode, errorCode, serverMessage, appMessage)
            in cases) {
          final service = AuthApiService(
            client: MockClient(
              (_) async => kakaoError(statusCode, errorCode, serverMessage),
            ),
          );

          await expectLater(
            service.kakaoLogin(accessToken: 'kakao-token'),
            throwsA(
              isA<AuthApiException>()
                  .having((error) => error.errorCode, 'errorCode', errorCode)
                  .having(
                    (error) => error.userMessage,
                    'userMessage',
                    appMessage,
                  ),
            ),
            reason: errorCode,
          );
        }
      },
    );

    test('withdraws a kakao account with only the fresh kakao token', () async {
      late http.Request captured;
      final service = AuthApiService(
        baseUrl: 'https://example.test',
        client: MockClient((request) async {
          captured = request;
          return jsonResponse({
            'status': 'success',
            'message': '회원 탈퇴가 완료되었습니다.',
          }, 200);
        }),
      );

      await service.withdrawWithKakao(
        accessToken: 'server-token',
        kakaoAccessToken: 'fresh-kakao-token',
      );

      expect(captured.url.path, '/auth/withdraw');
      expect(captured.headers['Authorization'], 'Bearer server-token');
      expect(jsonDecode(captured.body), {
        'kakao_access_token': 'fresh-kakao-token',
      });
    });
  });
}
