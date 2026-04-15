from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('strategies', '0002_add_phase_n_strategy_types'),
    ]

    operations = [
        migrations.AlterField(
            model_name='strategy',
            name='strategy_type',
            field=models.CharField(
                choices=[
                    ('ma_crossover', 'Moving Average Crossover'),
                    ('rsi_reversal', 'RSI Reversal'),
                    ('breakout', 'Breakout Strategy'),
                    ('mean_reversion', 'Mean Reversion'),
                    ('custom', 'Custom Strategy'),
                    ('ichimoku', 'Ichimoku Cloud'),
                    ('macd_divergence', 'MACD Divergence'),
                    ('stochastic', 'Stochastic Oscillator'),
                    ('ema_ribbon', 'EMA Ribbon'),
                    ('atr_breakout', 'ATR Channel Breakout'),
                    ('gold_xauusd', 'Gold XAUUSD'),
                ],
                default='ma_crossover',
                max_length=30,
            ),
        ),
    ]
