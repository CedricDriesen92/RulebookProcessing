
# NodeShape: SHACL Shape for FRO Article 2.1.1 - Compartment Sizing and Equipment
## Shape: SHACL Shape for FRO Article 2.1.1 - Compartment Sizing and Equipment
- **Overall Message**: Compartment does not meet the requirements of Article 2.1.1 regarding size, type, or safety equipment.
- **Applies to instances of**: **Fire Compartment**
- **AT LEAST ONE of the following must be true:**
  - **Option 1:**
    - **Property 'type'**
      - Must be exactly **Parking**.
  - **Option 2:**
    - **Property 'has area'**
      - Must be less than **2500**.
  - **Option 3:**
    - **Property 'isPartOfBuilding'**
      - **Additionally, values must satisfy:**
          - **Property 'isGroundFloorOnly'**
            - Must be exactly **true**.
          - **Property 'hasNumberOfCompartments'**
            - Must be exactly **1**.
    - **Property 'has area'**
      - Must be at most **3500**.
    - **Property 'hasLength'**
      - Must be at most **90**.
  - **Option 4:**
    - **Property 'hasAutomaticExtinguishingSystem'**
      - Must appear at least **1** time(s).
    - **Property 'hasSmokeAndHeatEvacuationSystem'**
      - Must appear at least **1** time(s).
- **Has SPARQL inference rule (constructs new data):**

