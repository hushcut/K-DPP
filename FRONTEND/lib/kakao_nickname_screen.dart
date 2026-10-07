// 처음 온 카카오 계정에 쓸 닉네임이 없을 때 닉네임을 받아 카카오 로그인(가입)을 마치는 화면입니다.
import 'package:flutter/material.dart';

import 'services/auth_api_service.dart';
import 'theme/app_palette.dart';
import 'utils/accessibility_announcer.dart';
import 'utils/auth_form_validators.dart';
import 'widgets/app_back_button.dart';
import 'widgets/app_banner.dart';
import 'widgets/auth_form_widgets.dart';

/// 서버가 `SOCIAL_NICKNAME_REQUIRED` 를 보냈을 때 로그인 화면이 띄우는 닉네임 화면입니다.
///
/// 받아 둔 [kakaoAccessToken] 에 닉네임을 붙여 `POST /auth/kakao` 를 다시 보내고(카카오 로그인은
/// 다시 하지 않음), 성공하면 그 [AuthResult] 를 돌려주며 닫힙니다. 뒤로 가거나 카카오 토큰이
/// 거부되면(만료 등 — 이 화면에서 고칠 수 없음) null 로 닫힙니다.
class KakaoNicknameScreen extends StatefulWidget {
  const KakaoNicknameScreen({
    super.key,
    required this.authApiService,
    required this.kakaoAccessToken,
  });

  final AuthApiService authApiService;
  final String kakaoAccessToken;

  @override
  State<KakaoNicknameScreen> createState() => _KakaoNicknameScreenState();
}

class _KakaoNicknameScreenState extends State<KakaoNicknameScreen> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final TextEditingController _nicknameController = TextEditingController();

  bool _isLoading = false;

  /// 서버가 닉네임을 거절한 이유입니다. 고치기 시작하면 지웁니다.
  String? _serverError;

  @override
  void dispose() {
    _nicknameController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_isLoading) return;

    final isValid = _formKey.currentState?.validate() ?? false;
    if (!isValid) return;

    setState(() => _isLoading = true);

    try {
      final result = await widget.authApiService.kakaoLogin(
        accessToken: widget.kakaoAccessToken,
        nickname: _nicknameController.text,
      );

      if (!mounted) return;

      Navigator.pop(context, result);
    } on AuthApiException catch (error) {
      if (!mounted) return;

      // 카카오 토큰이 만료·폐기됐으면 닉네임을 고쳐도 소용없어 카카오 로그인부터 다시 하게 한다.
      if (error.type == AuthApiErrorType.unauthorized ||
          error.errorCode == AuthErrorCode.socialTokenInvalid) {
        AppBanner.of(
          context,
        ).show(error.userMessage, kind: AppBannerKind.failure);
        Navigator.pop(context);
        return;
      }

      // 닉네임 규칙 위반(쓸 수 없는 문자 등)은 칸 아래에 두고 입력은 그대로 둔다.
      if (_isNicknameError(error)) {
        setState(() => _serverError = error.userMessage);
        announceFieldError(context, error.userMessage);
        return;
      }

      AppBanner.of(
        context,
      ).show(error.userMessage, kind: AppBannerKind.failure);
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  static bool _isNicknameError(AuthApiException error) {
    return switch (error.errorCode) {
      AuthErrorCode.badRequest ||
      AuthErrorCode.validationError ||
      AuthErrorCode.socialNicknameRequired => true,
      _ => false,
    };
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final backgroundColor = palette.background;
    final primaryText = palette.textPrimary;
    final secondaryText = palette.textSecondary;

    return PopScope(
      // 요청 중에 닫히면 서버에서 만들어진 계정의 응답을 받을 화면이 없어진다.
      canPop: !_isLoading,
      child: Scaffold(
        backgroundColor: backgroundColor,
        appBar: AppBar(
          backgroundColor: backgroundColor,
          elevation: 0,
          scrolledUnderElevation: 0,
          centerTitle: true,
          automaticallyImplyLeading: false,
          leadingWidth: 52,
          leading: Padding(
            padding: const EdgeInsets.only(left: 8),
            child: AppBackButton(
              onPressed: () {
                if (_isLoading) return;
                Navigator.pop(context);
              },
            ),
          ),
          title: Text(
            '닉네임 정하기',
            style: TextStyle(
              color: primaryText,
              fontSize: 20,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        body: SafeArea(
          child: Form(
            key: _formKey,
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Column(
                children: [
                  const SizedBox(height: 40),
                  Text(
                    '앱에서 쓸 닉네임을 정해 주세요',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: primaryText,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    // 한글은 글자 단위로 줄이 바뀌어 문장 경계에서 직접 나눕니다.
                    '카카오에서 쓸 수 있는 닉네임을 받지 못했어요.\n'
                    '2자 이상 50자 이하로 입력해 주세요.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 14,
                      color: secondaryText,
                      height: 1.5,
                    ),
                  ),
                  const SizedBox(height: 36),
                  TextFormField(
                    controller: _nicknameController,
                    autofocus: true,
                    textInputAction: TextInputAction.done,
                    autofillHints: const [AutofillHints.nickname],
                    validator: validateNicknameInput,
                    forceErrorText: _serverError,
                    onChanged: (_) {
                      if (_serverError == null) return;
                      setState(() => _serverError = null);
                    },
                    onFieldSubmitted: (_) => _submit(),
                    style: TextStyle(color: primaryText),
                    cursorColor: AppPalette.accent,
                    decoration: authInputDecoration(
                      context,
                      labelText: '닉네임',
                      hintText: '예: 홍길동',
                    ),
                  ),
                  const SizedBox(height: 32),
                  AuthSubmitButton(
                    label: '시작하기',
                    loadingSemanticsLabel: '카카오 계정으로 가입하는 중',
                    isLoading: _isLoading,
                    onPressed: _submit,
                  ),
                  const SizedBox(height: 24),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
