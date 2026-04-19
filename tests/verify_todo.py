import os
import sys
import asyncio
import json
from pathlib import Path

# Add src to sys.path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

async def test_store():
    print("\n--- Testing Store ---")
    from db.supabase_store import store
    print(f"Using store: {type(store).__name__}")
    
    # Test Business Profile
    profile = {
        "id": "test-user-123",
        "company_name": "Test Corp",
        "industry": "Electronics"
    }
    store.upsert_business_profile(profile)
    retrieved_profile = store.get_business_profile("test-user-123")
    print(f"Retrieved profile: {retrieved_profile['company_name']}")
    assert retrieved_profile['company_name'] == "Test Corp"

    # Test BOM creation
    bom_name = f"Test BOM {os.urandom(4).hex()}"
    bom = store.create_bom(bom_name)
    print(f"Created BOM: {bom['name']} (ID: {bom['id']})")
    
    # Test adding rows
    rows = [
        {"sku_code": "TEST-001", "description": "Microchip", "supplier_country": "China", "unit_cost_usd": 1.5, "annual_quantity": 1000},
        {"sku_code": "TEST-002", "description": "Resistor", "supplier_country": "Vietnam", "unit_cost_usd": 0.05, "annual_quantity": 50000}
    ]
    added_rows = store.add_bom_rows(bom['id'], rows)
    print(f"Added {len(added_rows)} rows to BOM")
    
    # Test listing BOMs
    boms = store.list_boms()
    print(f"Total BOMs in store: {len(boms)}")
    
    # Test getting BOM
    retrieved_bom = store.get_bom(bom['id'])
    print(f"Retrieved BOM has {len(retrieved_bom['rows'])} rows")
    
    assert retrieved_bom['id'] == bom['id']
    assert len(retrieved_bom['rows']) == 2
    print("Store tests PASSED.")

async def test_bom_mapper_lookups():
    print("\n--- Testing BOM Mapper Lookups ---")
    try:
        from agents.bom_mapper import BOMMapperAgent
        agent = BOMMapperAgent()
        
        if not os.getenv("GROQ_API_KEY"):
            print("Skipping description cleaning (no Groq key)")
        else:
            # Test cleaning description
            clean_desc = await agent._clean_description("TITAN-X E-BIKE MOTOR CONTROLLER FOR INTEGRATED CIRCUITS")
            print(f"Cleaned description: {clean_desc}")
        
        # Test Census lookup
        if not os.getenv("CENSUS_API_KEY"):
            print("Skipping Census lookup (no key)")
        else:
            try:
                census_res = await agent._census_schedule_b_lookup("lithium battery")
                print(f"Census lookup: {census_res.hs_code} (confidence: {census_res.confidence})")
            except Exception as e:
                print(f"Census lookup failed: {e}")

        # Test USITC lookup
        try:
            # 8542.31.0000 is for Integrated Circuits
            hts_res = await agent._usitc_hts_lookup("8542.31.0000")
            if hts_res:
                print(f"USITC lookup PASSED: Rate {hts_res.general_rate}")
            else:
                print("USITC lookup returned no results (might be transient)")
        except Exception as e:
            print(f"USITC lookup failed: {e}")
            
        print("BOM Mapper lookup tests completed.")
    except Exception as e:
        print(f"BOM Mapper tests FAILED: {e}")

async def test_federal_register():
    print("\n--- Testing Federal Register Client ---")
    try:
        from tools.federal_register import FederalRegisterClient
        client = FederalRegisterClient()
        # Corrected method name
        new_docs, audit = await client.fetch_tariff_documents(seen_ids=set())
        print(f"Fetched {len(new_docs)} documents from Federal Register")
        if new_docs:
            print(f"Latest doc: {new_docs[0]['title']}")
        print("Federal Register test PASSED.")
    except Exception as e:
        print(f"Federal Register test FAILED: {e}")

async def main():
    await test_store()
    await test_bom_mapper_lookups()
    await test_federal_register()

if __name__ == "__main__":
    asyncio.run(main())
