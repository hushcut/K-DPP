import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/closet_screen.dart';
import 'package:k_dpp/email_login_screen.dart';
import 'package:k_dpp/home_screen.dart';
import 'package:k_dpp/material_name_display_provider.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/password_reset_screen.dart';
import 'package:k_dpp/report_screen.dart';
import 'package:k_dpp/services/auth_api_service.dart';
import 'package:k_dpp/settings_screen.dart';
import 'package:k_dpp/signup_screen.dart';
import 'package:k_dpp/theme/app_palette.dart';
import 'package:k_dpp/theme_provider.dart';
import 'package:k_dpp/utils/clothing_type_catalog.dart';
import 'package:k_dpp/widgets/app_banner.dart';
import 'package:k_dpp/widgets/auth_form_widgets.dart';
import 'package:k_dpp/widgets/clothing_type_picker_sheet.dart';
import 'package:provider/provider.dart';

import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_storage.dart';

/// WCAG 2.x 대비율입니다.
double contrast(Color a, Color b) {
  final la = a.computeLuminance();
  final lb = b.computeLuminance();
  return (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05);
}

/// 화면에 실제로 그려진 글자색입니다(DefaultTextStyle 과 합친 뒤).
Color? textColor(WidgetTester tester, Finder text) =>
    tester.renderObject<RenderParagraph>(text).text.style?.color;

/// 버튼이 평소(눌리지 않은) 상태에서 칠하는 바탕색입니다.
Color? buttonFill(WidgetTester tester, Finder button) => tester
    .widget<ButtonStyleButton>(button)
    .style
    ?.backgroundColor
    ?.resolve(<WidgetState>{});

// C53·C54·C56: 흰 글자를 얹은 삭제·확인 버튼, 상태 글자, 팔레트를 우회한 회색 글자가 라이트 모드에서
// 본문 기준(4.5:1)에 못 미쳤다. 팔레트 값이 기준을 넘는지와, 각 화면이 그 값을 쓰는지 본다.
void main() {
  const aa = 4.5;

  group('팔레트 대비', () {
    test('흰 글자를 얹는 삭제·확인 버튼 바탕은 4.5:1 을 넘는다', () {
      expect(contrast(Colors.white, AppPalette.danger), greaterThan(aa));
      expect(contrast(Colors.white, AppPalette.success), greaterThan(aa));
    });

    for (final (name, palette) in [
      ('라이트', AppPalette.light),
      ('다크', AppPalette.dark),
    ]) {
      test('$name: 보조·경고·좋음·주의 글자는 화면 바탕과 카드에서 4.5:1 을 넘는다', () {
        for (final (label, color) in [
          ('보조', palette.textSecondary),
          ('경고', palette.dangerText),
          ('좋음', palette.successText),
          ('주의', palette.warningText),
        ]) {
          for (final background in [palette.background, palette.card]) {
            expect(
              contrast(color, background),
              greaterThan(aa),
              reason: '$label $color on $background',
            );
          }
        }
      });
    }

    // C55: 다크에서 바탕에 칠한 강조색 #4A4EFE 는 3.4:1(카드 3.1:1)이었다.
    test('바탕에 칠하는 강조색은 두 테마의 화면 바탕과 카드에서 4.5:1 을 넘는다', () {
      for (final palette in [AppPalette.light, AppPalette.dark]) {
        for (final background in [palette.background, palette.card]) {
          expect(
            contrast(palette.accentForeground, background),
            greaterThan(aa),
            reason: '${palette.accentForeground} on $background',
          );
        }
      }
      expect(AppPalette.light.accentForeground, AppPalette.accent);
    });

    test('수명 만료 글자는 옷장의 붉은 경고 카드 바탕에서도 4.5:1 을 넘는다', () {
      expect(
        contrast(AppPalette.light.dangerText, Colors.red.shade50),
        greaterThan(aa),
      );
      expect(
        contrast(AppPalette.dark.dangerText, const Color(0xFF2A1E1E)),
        greaterThan(aa),
      );
    });

    test('회색 입력 칸 안의 칸 이름과 예시 글자는 칸 바탕에서 4.5:1 을 넘는다', () {
      for (final (palette, fill) in [
        (AppPalette.light, const Color(0xFFF1F1F4)),
        (AppPalette.dark, const Color(0xFF1C1C1E)),
      ]) {
        expect(contrast(palette.inputLabel, fill), greaterThan(aa));
        expect(contrast(palette.inputHint, fill), greaterThan(aa));
      }
    });
  });

  group('화면이 팔레트 색을 쓴다(라이트)', () {
    const light = AppPalette.light;

    Clothes clothesWith(String title, {required int health}) => Clothes(
      title: title,
      category: '상의',
      health: health,
      materials: const {'면': 100},
      careInstruction: '찬물 세탁',
      carbonFootprint: 1.0,
    );

    Future<ClosetProvider> providerWith(List<Clothes> items) async {
      final provider = ClosetProvider(
        storage: FakeClosetStorage(),
        authSessionStorage: FakeAuthSessionStorage(),
      );
      for (final item in items) {
        await provider.addClothes(item);
      }
      return provider;
    }

    Future<void> pump(
      WidgetTester tester,
      ClosetProvider provider,
      Widget home,
    ) async {
      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: provider),
            ChangeNotifierProvider(create: (_) => ThemeProvider()),
            ChangeNotifierProvider(
              create: (_) => MaterialNameDisplayProvider(),
            ),
          ],
          child: MaterialApp(builder: AppBannerHost.builder, home: home),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('홈 건강도 퍼센트 글자는 좋음·주의·경고 글자색이다', (tester) async {
      for (final (health, expected) in [
        (71, light.successText),
        (41, light.warningText),
        (40, light.dangerText),
      ]) {
        final provider = await providerWith([
          clothesWith('셔츠', health: health),
        ]);
        await pump(tester, provider, const Scaffold(body: HomeScreen()));

        expect(textColor(tester, find.text('$health%')), expected);
      }
    });

    testWidgets('옷장 카드의 건강 상태 글자는 두 목록 모두 좋음·경고 글자색이고, 지우기 확인 버튼은 경고 바탕이다', (
      tester,
    ) async {
      final provider = await providerWith([
        clothesWith('튼튼한 셔츠', health: 88),
        clothesWith('낡은 니트', health: 10),
      ]);
      await pump(
        tester,
        provider,
        Scaffold(body: ClosetScreen(onOpenReport: (_) {})),
      );

      expect(textColor(tester, find.text('건강 상태: 88%')), light.successText);
      expect(textColor(tester, find.text('수명 만료 (배출 권장)')), light.dangerText);

      // '내 설정 순' 은 끌어 옮기는 다른 목록으로 그린다.
      await tester.tap(find.byTooltip('옷장 정렬'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('내 설정 순'));
      await tester.pumpAndSettle();
      expect(find.byType(ReorderableListView), findsOneWidget);
      expect(textColor(tester, find.text('건강 상태: 88%')), light.successText);
      expect(textColor(tester, find.text('수명 만료 (배출 권장)')), light.dangerText);

      await tester.tap(find.text('선택'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('낡은 니트'));
      await tester.pumpAndSettle();
      await tester.tap(find.byIcon(Icons.delete_outline));
      await tester.pumpAndSettle();

      expect(
        buttonFill(tester, find.widgetWithText(ElevatedButton, '삭제')),
        AppPalette.danger,
      );
    });

    testWidgets('리포트의 삭제 글자는 경고 글자색이고, 삭제 확인은 경고 바탕·폐기 안내 버튼은 확인 바탕이다', (
      tester,
    ) async {
      // 폐기 안내 시트는 기본 시험 화면(800×600)에선 4.5px 넘쳐, 폰 크기(390×844)로 연다.
      tester.view.physicalSize = const Size(1170, 2532);
      tester.view.devicePixelRatio = 3;
      addTearDown(tester.view.reset);
      final provider = await providerWith([clothesWith('셔츠', health: 80)]);
      await pump(tester, provider, const Scaffold(body: ReportScreen()));

      expect(textColor(tester, find.text('이 의류 삭제하기')), light.dangerText);

      final disposal = find.widgetWithText(ElevatedButton, '올바른 폐기 방법 보기');
      expect(buttonFill(tester, disposal), AppPalette.success);

      await tester.ensureVisible(find.text('이 의류 삭제하기'));
      await tester.tap(find.text('이 의류 삭제하기'));
      await tester.pumpAndSettle();
      expect(
        buttonFill(tester, find.widgetWithText(ElevatedButton, '삭제')),
        AppPalette.danger,
      );
      await tester.tap(find.text('취소'));
      await tester.pumpAndSettle();

      await tester.ensureVisible(disposal);
      await tester.tap(disposal);
      await tester.pumpAndSettle();
      expect(
        buttonFill(tester, find.widgetWithText(ElevatedButton, '확인했어요')),
        AppPalette.success,
      );
    });

    testWidgets('설정의 섹션 제목은 보조 글자색, 회원 탈퇴는 경고 글자색이고, 탈퇴 버튼은 경고 바탕이다', (
      tester,
    ) async {
      final provider = await providerWith(const []);
      await provider.setAuthenticatedUser(
        nickname: '홍길동',
        email: 'a@example.com',
        accessToken: 'access-token',
        expiresInSeconds: 3600,
      );
      await pump(
        tester,
        provider,
        SettingsScreen(
          authApiService: AuthApiService(
            baseUrl: 'https://example.test',
            client: MockClient((_) async => http.Response('{}', 500)),
          ),
        ),
      );

      expect(textColor(tester, find.text('내 정보')), light.textSecondary);

      final withdraw = find.text('회원 탈퇴');
      await tester.scrollUntilVisible(
        withdraw,
        220,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      expect(textColor(tester, withdraw), light.dangerText);

      await tester.tap(withdraw);
      await tester.pumpAndSettle();
      expect(
        buttonFill(tester, find.widgetWithText(ElevatedButton, '탈퇴')),
        AppPalette.danger,
      );
    });

    testWidgets(
      '의류 종류 시트의 안내 문장은 보조 글자색, 직접 입력 오류는 경고 글자색이고, "다시 촬영" 확인은 경고 바탕이다',
      (tester) async {
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: Builder(
                builder: (context) => Center(
                  child: ElevatedButton(
                    onPressed: () => showClothingTypePickerSheet(
                      context: context,
                      options: ClothingTypeCatalog.options,
                      initialSelection: ClothingTypeCatalog.defaultOption,
                      discardPrompt:
                          ClothingTypePickerDiscardPrompt.analysisResult,
                    ),
                    child: const Text('시트 열기'),
                  ),
                ),
              ),
            ),
          ),
        );
        await tester.tap(find.text('시트 열기'));
        await tester.pumpAndSettle();
        expect(
          textColor(tester, find.text('탄소발자국 계산에 사용할 의류 무게 범위를 선택해 주세요.')),
          light.textSecondary,
        );

        await tester.tap(find.text('다시 촬영'));
        await tester.pumpAndSettle();
        final confirm = find.descendant(
          of: find.byType(AlertDialog),
          matching: find.widgetWithText(ElevatedButton, '다시 촬영'),
        );
        expect(buttonFill(tester, confirm), AppPalette.danger);
        await tester.tap(find.text('선택 계속하기'));
        await tester.pumpAndSettle();

        await tester.scrollUntilVisible(find.text('직접 입력'), 100);
        await tester.ensureVisible(find.text('직접 입력'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('직접 입력'));
        await tester.pumpAndSettle();
        expect(
          textColor(
            tester,
            find.text('실제 무게를 알고 있다면 더 정확하게 탄소발자국을 계산할 수 있어요.'),
          ),
          light.textSecondary,
        );
        await tester.tap(find.widgetWithText(ElevatedButton, '적용하기'));
        await tester.pumpAndSettle();
        expect(
          textColor(tester, find.text('의류 종류를 입력해 주세요.')),
          light.dangerText,
        );
      },
    );

    testWidgets('로그인·가입·비밀번호 찾기의 안내 문장은 보조 글자색이고, 입력 칸 이름·예시는 입력 칸 글자색이다', (
      tester,
    ) async {
      final provider = await providerWith(const []);
      for (final (screen, sentence) in [
        (const EmailLoginScreen(), '계정 정보를 입력하고 서비스를 시작해 보세요.'),
        (const SignupScreen(), '이메일로 받은 인증번호와 계정 정보를 입력해 주세요.'),
        (
          const PasswordResetScreen(),
          '가입한 이메일로 받은 인증번호를 넣어 주세요.\n다른 기기의 로그인도 모두 풀려요.',
        ),
      ]) {
        await pump(tester, provider, screen);
        expect(textColor(tester, find.text(sentence)), light.textSecondary);
      }

      late InputDecoration decoration;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) {
              decoration = authInputDecoration(
                context,
                labelText: '이메일',
                hintText: 'example@email.com',
              );
              return const SizedBox();
            },
          ),
        ),
      );
      expect(decoration.labelStyle?.color, light.inputLabel);
      expect(decoration.hintStyle?.color, light.inputHint);
    });
  });

  group('화면이 팔레트 색을 쓴다(다크)', () {
    testWidgets('옷장의 선택된 탭·탭 밑줄·정렬 아이콘은 다크용 강조색이다', (
      tester,
    ) async {
      final provider = ClosetProvider(
        storage: FakeClosetStorage(),
        authSessionStorage: FakeAuthSessionStorage(),
      );
      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: provider),
            ChangeNotifierProvider(create: (_) => ThemeProvider()),
            ChangeNotifierProvider(
              create: (_) => MaterialNameDisplayProvider(),
            ),
          ],
          child: MaterialApp(
            theme: ThemeData(brightness: Brightness.dark),
            builder: AppBannerHost.builder,
            home: Scaffold(body: ClosetScreen(onOpenReport: (_) {})),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final tabBar = tester.widget<TabBar>(find.byType(TabBar));
      expect(tabBar.labelColor, AppPalette.dark.accentForeground);
      expect(tabBar.indicatorColor, AppPalette.dark.accentForeground);
      expect(
        tester.widget<Icon>(find.byIcon(Icons.sort)).color,
        AppPalette.dark.accentForeground,
      );
      expect(AppPalette.dark.accentForeground, isNot(AppPalette.accent));
    });
  });
}
