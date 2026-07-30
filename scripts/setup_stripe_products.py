import json
import os
import sys

# Try to import stripe, if not installed print an error with instructions
try:
    import stripe
except ImportError:
    print("[ERRO] A biblioteca 'stripe' nao esta instalada.")
    print("Instale rodando: pip install stripe")
    sys.exit(1)

# Ensure the user has passed their secret key as an argument or env var
STRIPE_SECRET = os.getenv("STRIPE_SECRET_KEY")

# Fallback 1: Command line argument
if not STRIPE_SECRET and len(sys.argv) > 1:
    STRIPE_SECRET = sys.argv[1]

# Fallback 2: Read manually from .env file
if not STRIPE_SECRET:
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("STRIPE_SECRET_KEY="):
                    STRIPE_SECRET = line.split("=", 1)[1].strip()
                    break

if not STRIPE_SECRET:
    print("[ERRO] STRIPE_SECRET_KEY nao foi encontrada no ambiente, nos argumentos nem no .env.")
    print("Uso: python scripts/setup_stripe_products.py sk_test_...")
    sys.exit(1)

stripe.api_key = STRIPE_SECRET

def load_pricing() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "pricing.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f).get("plans", {})
    except Exception as e:
        print(f"[ERRO] Erro ao ler pricing.json: {e}")
        sys.exit(1)

def main():
    print("[INFO] Iniciando configuracao automatica da Stripe...\n")
    plans = load_pricing()
    
    price_map = {}
    
    for plan_key, details in plans.items():
        price_usd = details.get("price_usd", 0.0)
        
        if price_usd <= 0:
            print(f"[PULANDO] '{plan_key}' (Plano Gratuito)")
            continue
            
        print(f"[PROCESSANDO] Configurando '{plan_key}' (${price_usd}/mes)...")
        
        # 1. Create or Find the Product
        product_name = f"Tiffany {plan_key.replace('_', ' ').title()}"
        try:
            product = stripe.Product.create(
                name=product_name,
                description=f"Plano Premium para Tiffany Bot: {plan_key}",
                metadata={"internal_package": plan_key}
            )
            print(f"  [OK] Produto criado: {product.id}")
            
            # 2. Create the Price (Recurring Monthly)
            amount_cents = int(price_usd * 100)
            price = stripe.Price.create(
                product=product.id,
                unit_amount=amount_cents,
                currency="usd",
                recurring={"interval": "month"},
                metadata={"internal_package": plan_key}
            )
            print(f"  [OK] Preco criado: {price.id}")
            
            price_map[price.id] = plan_key
            
        except Exception as e:
            print(f"  [ERRO] Erro ao configurar '{plan_key}': {e}")
            sys.exit(1)
            
    print("\n[SUCESSO] Configuracao da Stripe concluida com sucesso!")
    print("\n=======================================================")
    print("COPIE E COLE ISSO NO SEU ARQUIVO .env:")
    print("=======================================================\n")
    
    # Generate the JSON map string
    map_str = json.dumps(price_map)
    print(f"STRIPE_PRICE_MAP='{map_str}'")
    
    print("\n=======================================================")
    print("Pronto! Agora a Tiffany sabera exatamente qual pacote ativar")
    print("quando o Webhook da Stripe for acionado.")
    
if __name__ == "__main__":
    main()
