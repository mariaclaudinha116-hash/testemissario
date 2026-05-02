"""
Backend Missário — Serverless Function para Vercel.
Compatível com @vercel/python (ASGI via Mangum).
"""
import os
import re
import requests as http
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from mangum import Mangum

# ── AppMax ──
APPMAX_TOKEN = os.environ.get(
    "APPMAX_TOKEN", "0929BBC4-3A929ADA-495A1CCC-BC84EAAF"
).strip()
APPMAX_BASE = "https://admin.appmax.com.br/api/v3"

app = FastAPI(title="Missário Checkout")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Modelos ──
class CartItem(BaseModel):
    id: str
    name: str
    price: str
    qty: int
    img: str = ""


class CheckoutData(BaseModel):
    nome: str
    sobrenome: str
    email: str
    telefone: str
    cpf: str
    cep: str
    rua: str
    numero: str
    complemento: str = ""
    bairro: str
    cidade: str
    estado: str
    payment_method: str  # "pix" | "credit_card"
    products: List[dict]
    total_cents: int
    # Cartão (opcionais)
    card_number: Optional[str] = None
    card_name: Optional[str] = None
    card_month: Optional[int] = None
    card_year: Optional[int] = None
    card_cvv: Optional[str] = None
    installments: int = 1


def digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def price_to_float(s: str) -> float:
    clean = s.replace("R$", "").strip().replace(".", "").replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return 0.0


# ── Checkout endpoint ──
@app.post("/api/checkout")
async def checkout(data: CheckoutData, request: Request):
    ip = "127.0.0.1"
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        ip = fwd.split(",")[0].strip()
    elif request.client:
        ip = request.client.host

    try:
        # ═══ 1. Criar cliente na AppMax ═══
        cust_payload = {
            "access-token": APPMAX_TOKEN,
            "firstname": data.nome.strip(),
            "lastname": data.sobrenome.strip(),
            "email": data.email.strip(),
            "telephone": digits(data.telefone),
            "postcode": digits(data.cep),
            "address_street": data.rua.strip(),
            "address_street_number": data.numero.strip(),
            "address_street_complement": data.complemento.strip(),
            "address_street_district": data.bairro.strip(),
            "address_city": data.cidade.strip(),
            "address_state": data.estado.upper().strip(),
            "ip": ip,
        }

        cust_res = http.post(
            f"{APPMAX_BASE}/customer", json=cust_payload, timeout=30
        )
        cust_json = cust_res.json()

        customer_id = None
        if isinstance(cust_json.get("data"), dict):
            customer_id = cust_json["data"].get("id")
        if not customer_id:
            return JSONResponse(
                {
                    "success": False,
                    "error": "Erro ao registrar cliente. Verifique seus dados.",
                    "details": cust_json,
                },
                status_code=400,
            )

        # ═══ 2. Criar pedido na AppMax ═══
        total_reais = data.total_cents / 100

        order_products = []
        for item in data.products:
            order_products.append(
                {
                    "sku": item.get("id", "PROD"),
                    "name": item.get("name", "Produto"),
                    "qty": item.get("qty", 1),
                    "price": price_to_float(item.get("price", "0")),
                }
            )

        order_payload = {
            "access-token": APPMAX_TOKEN,
            "customer_id": customer_id,
            "total": total_reais,
            "shipping": 0,
            "products": order_products,
        }

        order_res = http.post(
            f"{APPMAX_BASE}/order", json=order_payload, timeout=30
        )
        order_json = order_res.json()

        order_id = None
        if isinstance(order_json.get("data"), dict):
            order_id = order_json["data"].get("id")
        if not order_id:
            return JSONResponse(
                {
                    "success": False,
                    "error": "Erro ao criar pedido.",
                    "details": order_json,
                },
                status_code=400,
            )

        # ═══ 3. Processar pagamento ═══
        cpf_clean = digits(data.cpf)

        if data.payment_method == "pix":
            pay_payload = {
                "access-token": APPMAX_TOKEN,
                "cart": {"order_id": order_id},
                "customer": {"customer_id": customer_id},
                "payment": {
                    "pix": {
                        "document_number": cpf_clean,
                    }
                },
            }

            pay_res = http.post(
                f"{APPMAX_BASE}/payment/pix", json=pay_payload, timeout=30
            )
            pay_json = pay_res.json()

            pay_data = pay_json.get("data")
            if isinstance(pay_data, dict) and pay_data.get("pix_emv"):
                return JSONResponse(
                    {
                        "success": True,
                        "method": "pix",
                        "order_id": order_id,
                        "pix_qrcode": pay_data.get("pix_qrcode", ""),
                        "pix_emv": pay_data.get("pix_emv", ""),
                        "pix_expiration": pay_data.get(
                            "pix_expiration_date", ""
                        ),
                    }
                )
            else:
                err_text = pay_json.get("text", "Erro ao gerar PIX.")
                if "inv" in err_text.lower() and "cpf" in err_text.lower():
                    err_text = "CPF invalido. Verifique o numero digitado."
                return JSONResponse(
                    {
                        "success": False,
                        "error": err_text,
                        "details": pay_json,
                    },
                    status_code=400,
                )

        elif data.payment_method == "credit_card":
            if not all(
                [
                    data.card_number,
                    data.card_name,
                    data.card_month,
                    data.card_year,
                    data.card_cvv,
                ]
            ):
                return JSONResponse(
                    {
                        "success": False,
                        "error": "Preencha todos os dados do cartão.",
                    },
                    status_code=400,
                )

            pay_payload = {
                "access-token": APPMAX_TOKEN,
                "cart": {"order_id": order_id},
                "customer": {"customer_id": customer_id},
                "payment": {
                    "CreditCard": {
                        "number": digits(data.card_number),
                        "cvv": data.card_cvv.strip(),
                        "month": data.card_month,
                        "year": data.card_year,
                        "name": data.card_name.upper().strip(),
                        "document_number": data.cpf.strip(),
                        "installments": data.installments,
                        "soft_descriptor": "MISSARIO",
                    }
                },
            }

            pay_res = http.post(
                f"{APPMAX_BASE}/payment/credit-card",
                json=pay_payload,
                timeout=30,
            )
            pay_json = pay_res.json()

            pay_data = pay_json.get("data")
            approved = ["aprovado", "integrado", "autorizado"]

            if pay_data and pay_data.get("status") in approved:
                return JSONResponse(
                    {
                        "success": True,
                        "method": "credit_card",
                        "order_id": order_id,
                        "status": pay_data["status"],
                        "reference": pay_data.get("pay_reference", ""),
                    }
                )
            else:
                err = pay_json.get("text", "Transação não autorizada.")
                return JSONResponse(
                    {
                        "success": False,
                        "error": err,
                        "details": pay_json,
                    },
                    status_code=400,
                )
        else:
            return JSONResponse(
                {"success": False, "error": "Método de pagamento inválido."},
                status_code=400,
            )

    except http.exceptions.Timeout:
        return JSONResponse(
            {
                "success": False,
                "error": "Timeout na comunicação com o gateway de pagamento.",
            },
            status_code=504,
        )
    except http.exceptions.ConnectionError:
        return JSONResponse(
            {
                "success": False,
                "error": "Erro de conexão com o gateway. Tente novamente.",
            },
            status_code=502,
        )
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": f"Erro interno: {str(e)}"},
            status_code=500,
        )


@app.get("/api/order-status/{order_id}")
async def order_status(order_id: int):
    try:
        res = http.get(
            f"{APPMAX_BASE}/order",
            params={"access-token": APPMAX_TOKEN, "order_id": order_id},
            timeout=15,
        )
        data = res.json()
        status = "pending"
        if isinstance(data.get("data"), dict):
            status = data["data"].get("status", "pending")
        return JSONResponse({"order_id": order_id, "status": status})
    except Exception:
        return JSONResponse({"order_id": order_id, "status": "unknown"})


# ── Handler Vercel (ASGI via Mangum) ──
handler = Mangum(app, lifespan="off")
