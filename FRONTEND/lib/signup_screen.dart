// 이메일 인증번호를 확인해 신규 계정을 서버에 등록하고 로그인 화면으로 연결하는 파일입니다.
import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'services/auth_api_service.dart';
import 'theme/app_palette.dart';
import 'utils/auth_form_validators.dart';
import 'widgets/app_back_button.dart';
import 'widgets/app_banner.dart';
import 'widgets/auth_form_widgets.dart';
import 'widgets/email_code_section.dart';
import 'widgets/number_keyboard_toolbar.dart';

/// 이메일·인증번호·닉네임·비밀번호를 한 화면에서 입력받는 회원가입 폼 화면입니다.
///
/// 서버에 번호만 확인하는 API 가 없어 번호는 가입 요청과 함께 확인됩니다. 그래서 두 단계로
/// 나누지 않고, 틀린 번호는 이 화면의 번호 칸에 바로 보입니다(DECISIONS 170 ①).
class SignupScreen extends StatefulWidget {
  const SignupScreen({super.key, this.authApiService, this.now});

  /// 이메일 로그인 화면에서 진입했음을 알리는 경로 인자입니다.
  /// 이 값이 전달되면 로그인 화면을 새로 쌓지 않고 pop으로 되돌아갑니다.
  static const String fromEmailLoginArgument = 'from-email-login';

  final AuthApiService? authApiService;

  /// 인증번호 남은 시간을 셀 시계입니다. 테스트만 바꿔 끼웁니다.
  final DateTime Function()? now;

  @override
  State<SignupScreen> createState() => _SignupScreenState();
}

class _SignupScreenState extends State<SignupScreen> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final GlobalKey<FormFieldState<String>> _emailFieldKey =
      GlobalKey<FormFieldState<String>>();
  final GlobalKey<EmailCodeSectionState> _codeSectionKey =
      GlobalKey<EmailCodeSectionState>();

  final TextEditingController _nicknameController = TextEditingController();
  final TextEditingController _emailController = TextEditingController();
  final TextEditingController _codeController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  final TextEditingController _confirmPasswordController =
      TextEditingController();
  final FocusNode _codeFocusNode = FocusNode();
  final FocusNode _nicknameFocusNode = FocusNode();
  final FocusNode _passwordFocusNode = FocusNode();
  final FocusNode _confirmPasswordFocusNode = FocusNode();
  late final AuthApiService _authApiService;

  bool _isLoading = false;
  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;

  @override
  void initState() {
    super.initState();
    _authApiService = widget.authApiService ?? AuthApiService();
  }

  @override
  void dispose() {
    _nicknameController.dispose();
    _emailController.dispose();
    _codeController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    _codeFocusNode.dispose();
    _nicknameFocusNode.dispose();
    _passwordFocusNode.dispose();
    _confirmPasswordFocusNode.dispose();
    super.dispose();
  }

  String? _validateNickname(String? value) {
    final text = value?.trim() ?? '';

    if (text.isEmpty) {
      return '닉네임을 입력해 주세요';
    }

    if (text.length < 2) {
      return '닉네임은 2자 이상 입력해 주세요';
    }

    return null;
  }

  /// 이메일 로그인에서 진입했으면 pop으로 되돌아가 화면이 중복으로 쌓이지 않게 하고,
  /// 그 외 경로에서는 기존처럼 로그인 화면으로 교체 이동합니다.
  void _navigateBackToEmailLogin({String? email}) {
    final cameFromEmailLogin =
        ModalRoute.of(context)?.settings.arguments ==
        SignupScreen.fromEmailLoginArgument;

    if (cameFromEmailLogin && Navigator.canPop(context)) {
      Navigator.pop(context, email);
      return;
    }

    Navigator.pushReplacementNamed(context, '/email-login', arguments: email);
  }

  /// 폼이 유효할 때 가입 API를 호출하고, 성공하면 이메일을 로그인 화면에 전달합니다.
  Future<void> _handleSignup() async {
    final isValid = _formKey.currentState?.validate() ?? false;
    if (!isValid) return;

    final email = _emailController.text.trim();

    setState(() {
      _isLoading = true;
    });

    try {
      await _authApiService.signup(
        nickname: _nicknameController.text.trim(),
        email: email,
        password: _passwordController.text,
        code: _codeController.text,
      );

      if (!mounted) return;

      AppBanner.of(context).show(
        '회원가입이 완료됐어요. 로그인해 주세요.',
        kind: AppBannerKind.success,
      );

      _navigateBackToEmailLogin(email: email);
    } on AuthApiException catch (error) {
      if (!mounted) return;

      // 번호 오류는 번호 칸에 붙이고, 그 밖의 거절·통신 실패는 배너로 알립니다.
      final shownOnCodeField =
          _codeSectionKey.currentState?.showSubmitError(error) ?? false;
      if (shownOnCodeField) return;

      AppBanner.of(context).show(error.userMessage, kind: AppBannerKind.failure);
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  // iOS 숫자 키패드에는 다음 키가 없어, 번호 칸에 포커스가 있는 동안 키보드 위에 ∧·∨·[완료] 막대를 그립니다.
  Widget _buildNumberKeyboardToolbar(BuildContext context) {
    if (!NumberKeyboardToolbar.isNeeded(context)) {
      return const SizedBox.shrink();
    }

    return ListenableBuilder(
      listenable: _codeFocusNode,
      builder: (context, _) {
        if (!_codeFocusNode.hasFocus) return const SizedBox.shrink();

        return NumberKeyboardToolbar(
          onNext: _nicknameFocusNode.requestFocus,
          onDone: _codeFocusNode.unfocus,
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);
    final backgroundColor = palette.background;
    final primaryText = palette.textPrimary;
    final secondaryText = isDark
        ? const Color(0xFFD1D1D6)
        : const Color(0xFF8C8C8C);
    final iconColor = isDark
        ? const Color(0xFFB8B8BE)
        : const Color(0xFF8C8C8C);

    return Scaffold(
      backgroundColor: backgroundColor,
      appBar: AppBar(
        backgroundColor: backgroundColor,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: true,
        automaticallyImplyLeading: false,
        leadingWidth: 52,
        leading: const Padding(
          padding: EdgeInsets.only(left: 8),
          child: AppBackButton(),
        ),
        title: Text(
          '회원가입',
          style: TextStyle(
            color: primaryText,
            fontSize: 20,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      body: SafeArea(
        // 본문이 키보드만큼 줄어들므로, 맨 아래에 둔 막대가 키보드 바로 위에 놓입니다.
        child: Column(
          children: [
            Expanded(
              child: Form(
                key: _formKey,
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    return SingleChildScrollView(
                      padding: const EdgeInsets.symmetric(horizontal: 24),
                      child: ConstrainedBox(
                        // 아래 인셋(자판 등)이 앱바 아래를 다 덮으면 maxHeight 가 0 이 되므로
                        // 빼고 남은 값이 음수가 되지 않게 0 에서 멈춥니다.
                        constraints: BoxConstraints(
                          minHeight: math.max(0.0, constraints.maxHeight - 12),
                        ),
                        child: IntrinsicHeight(
                          child: Column(
                            children: [
                              const SizedBox(height: 40),
                              Text(
                                'K-DPP 계정을 만들어보세요',
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.w700,
                                  color: primaryText,
                                ),
                              ),
                              const SizedBox(height: 10),
                              Text(
                                '이메일로 받은 인증번호와 계정 정보를 입력해 주세요.',
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  fontSize: 14,
                                  color: secondaryText,
                                  height: 1.5,
                                ),
                              ),
                              const SizedBox(height: 36),
                              TextFormField(
                                key: _emailFieldKey,
                                controller: _emailController,
                                keyboardType: TextInputType.emailAddress,
                                textInputAction: TextInputAction.next,
                                autofillHints: const [AutofillHints.email],
                                autocorrect: false,
                                validator: validateEmailInput,
                                style: TextStyle(color: primaryText),
                                cursorColor: AppPalette.accent,
                                decoration: authInputDecoration(
                                  context,
                                  labelText: '이메일',
                                  hintText: 'honggildong@example.com',
                                ),
                              ),
                              const SizedBox(height: 12),
                              EmailCodeSection(
                                key: _codeSectionKey,
                                purpose: EmailCodePurpose.signup,
                                authApiService: _authApiService,
                                emailFieldKey: _emailFieldKey,
                                emailController: _emailController,
                                codeController: _codeController,
                                codeFocusNode: _codeFocusNode,
                                enabled: !_isLoading,
                                onCodeSubmitted: (_) =>
                                    _nicknameFocusNode.requestFocus(),
                                now: widget.now ?? DateTime.now,
                              ),
                              const SizedBox(height: 16),
                              TextFormField(
                                controller: _nicknameController,
                                focusNode: _nicknameFocusNode,
                                textInputAction: TextInputAction.next,
                                autofillHints: const [AutofillHints.nickname],
                                validator: _validateNickname,
                                style: TextStyle(color: primaryText),
                                cursorColor: AppPalette.accent,
                                decoration: authInputDecoration(
                                  context,
                                  labelText: '닉네임',
                                  hintText: '예: 홍길동',
                                ),
                              ),
                              const SizedBox(height: 16),
                              TextFormField(
                                controller: _passwordController,
                                focusNode: _passwordFocusNode,
                                obscureText: _obscurePassword,
                                textInputAction: TextInputAction.next,
                                // 기본 '다음'은 칸 안의 눈 아이콘으로 가 키보드가 내려갑니다.
                                onEditingComplete:
                                    _confirmPasswordFocusNode.requestFocus,
                                autofillHints: const [
                                  AutofillHints.newPassword,
                                ],
                                enableSuggestions: false,
                                autocorrect: false,
                                validator: validateNewPassword,
                                style: TextStyle(color: primaryText),
                                cursorColor: AppPalette.accent,
                                decoration: authInputDecoration(
                                  context,
                                  labelText: '비밀번호',
                                  hintText: '8자 이상 입력',
                                  suffixIcon: IconButton(
                                    onPressed: () {
                                      setState(() {
                                        _obscurePassword = !_obscurePassword;
                                      });
                                    },
                                    tooltip: _obscurePassword
                                        ? '비밀번호 표시'
                                        : '비밀번호 숨기기',
                                    icon: Icon(
                                      _obscurePassword
                                          ? Icons.visibility_off_outlined
                                          : Icons.visibility_outlined,
                                      color: iconColor,
                                    ),
                                  ),
                                ),
                              ),
                              const SizedBox(height: 16),
                              TextFormField(
                                controller: _confirmPasswordController,
                                focusNode: _confirmPasswordFocusNode,
                                obscureText: _obscureConfirmPassword,
                                textInputAction: TextInputAction.done,
                                autofillHints: const [
                                  AutofillHints.newPassword,
                                ],
                                enableSuggestions: false,
                                autocorrect: false,
                                validator: (value) =>
                                    validatePasswordConfirmation(
                                      value,
                                      _passwordController.text,
                                    ),
                                style: TextStyle(color: primaryText),
                                cursorColor: AppPalette.accent,
                                decoration: authInputDecoration(
                                  context,
                                  labelText: '비밀번호 확인',
                                  hintText: '비밀번호 다시 입력',
                                  suffixIcon: IconButton(
                                    onPressed: () {
                                      setState(() {
                                        _obscureConfirmPassword =
                                            !_obscureConfirmPassword;
                                      });
                                    },
                                    tooltip: _obscureConfirmPassword
                                        ? '비밀번호 확인 표시'
                                        : '비밀번호 확인 숨기기',
                                    icon: Icon(
                                      _obscureConfirmPassword
                                          ? Icons.visibility_off_outlined
                                          : Icons.visibility_outlined,
                                      color: iconColor,
                                    ),
                                  ),
                                ),
                                onFieldSubmitted: (_) {
                                  if (!_isLoading) {
                                    _handleSignup();
                                  }
                                },
                              ),
                              const SizedBox(height: 32),
                              AuthSubmitButton(
                                label: '회원가입',
                                loadingSemanticsLabel: '회원가입 처리 중',
                                isLoading: _isLoading,
                                onPressed: _handleSignup,
                              ),
                              const SizedBox(height: 18),
                              AuthLinkButton(
                                label: '이미 계정이 있으신가요? 로그인',
                                onPressed: () => _navigateBackToEmailLogin(),
                              ),
                              const Spacer(),
                              const SizedBox(height: 24),
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
            ),
            _buildNumberKeyboardToolbar(context),
          ],
        ),
      ),
    );
  }
}
