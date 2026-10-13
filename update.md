# AgriSentinel System Enhancements & Panel Recommendations

## New Working Title
**AgriSentinel: An AI-Powered Crop Protection Robot for Smart Pest Detection, Plant Health Assessment, and Pest-Specific Pesticide Recommendation**

---

## Suggestions and Proposed Enhancements
Based on the suggestions and recommendations from the panel, the following enhancements should be considered for the AgriSentinel prototype, AI system, database, web application, and mobile application:

---

### 1. Prototype and Robot Structure
* Modify the physical prototype into a simplified skeletal/imaging-probe design, such as a standing stick or pole positioned near the crop.
* The structure should primarily support the camera/imaging sensors and other necessary components.
* Keep the design practical, lightweight, and focused on the system's primary function: capturing crop images for AI analysis and providing appropriate pest-management recommendations.

---

### 2. Replace Frequency-Based Pest Control
* Remove or reconsider the original concept of releasing a specific frequency to control detected pests.
* Instead, once a pest is identified, the AI should provide a specific recommended insecticide/pesticide intended for that particular pest, subject to appropriate agricultural guidance.
* The recommendation should include relevant information such as:
  * Detected pest
  * Recommended pesticide/insecticide
  * Intended target pest
  * Recommended application information, where reliable data is available
  * Appropriate safety precautions

---

### 3. AI Pest Detection Enhancement
* Improve the AI model's ability to detect and identify agricultural pests accurately.
* Expand the dataset with additional pest images, including different:
  * Pest sizes
  * Growth stages
  * Viewing angles
  * Lighting conditions
  * Backgrounds
  * Levels of infestation

---

### 4. Camera and Image Quality Enhancement
* Upgrade the camera or imaging component to improve the quality of images captured by the robot.
* Ensure that the camera can capture sufficiently clear images for:
  * Pest identification
  * Plant disease/mold detection
  * Plant health assessment
  * Identification of specific pest characteristics
* Consider image quality under different environmental conditions, including varying lighting and distance from the plant.

---

### 5. Pest-Specific Pesticide Recommendation
* Develop an AI-supported recommendation component that maps an identified pest to an appropriate pesticide/insecticide recommendation.
* The system should avoid simply recommending a general pesticide. It should identify the detected pest first and then retrieve the corresponding recommendation from the system's agricultural knowledge base/database.
* Recommendations should be based on reliable agricultural references and should include appropriate warnings and usage information.
* The system should clearly indicate when the AI is uncertain about the pest identification rather than providing an unreliable recommendation.

---

### 6. Database / DBMS Integration
* Integrate the AI system with a Database Management System (DBMS).
* After the robot detects pests and generates an AI assessment, the relevant information should be stored automatically in the database.
* Possible information to store includes:
  * Detection date and time
  * Crop type
  * Detected pest
  * Number of detected pests
  * Detection confidence
  * Plant health condition
  * Detected disease/mold, if applicable
  * AI-generated pesticide/insecticide recommendation
  * Image captured during detection
  * Location or designated farm/field area, if available
* This will allow users to review historical detection records and monitor pest conditions over time.

---

### 7. Web Application Enhancement
* Enhance the web application to provide a centralized monitoring and management platform.
* The web application should allow users to:
  * View detected pests
  * View the number of detected pests
  * View pest detection history
  * View plant health assessments
  * View recommended pest-control products
  * View captured images
  * Monitor different crops or farm areas
  * Access historical data stored in the DBMS
  * Monitor changes in pest activity over time

---

### 8. Mobile Application Enhancement
* Improve the mobile application so that users can conveniently monitor the robot and receive detection results.
* The application should provide:
  * Pest detection notifications
  * Number of pests detected
  * Identified pest type
  * Plant health status
  * Recommended pesticide/insecticide
  * Detection history
  * Captured images
  * Important alerts when significant pest activity is detected

---

### 9. Automatic Stopping Mechanism
* Integrate a stopping mechanism into the robot's operation.
* Once the AI detects a target pest or reaches a predefined detection condition, the robot should temporarily stop or pause its movement.
* The purpose is to allow the camera to capture a clearer image and perform a more reliable analysis.
* The stopping behavior should be configurable depending on the detected pest and system requirements.

---

### 10. Pest Count and Infestation Monitoring
* The AI should not only identify the pest but also estimate or count how many pests are present within the captured image or detection area.
* The detected pest count should be displayed on both the web and mobile applications.
* The system may categorize infestation levels, provided that the classification is properly defined and validated.

---

### 11. Rice Stem Borer Detection
* Add a specialized detection capability for rice stem borer, particularly focusing on identifying relevant signs or characteristics associated with the pest's presence.
* The system should investigate how to identify the adult/mother stem borer and/or other observable indicators of stem-borer infestation on rice plants.
* Since some pest stages may not be directly visible, the system should also consider visible symptoms or damage patterns on the rice plant as supporting indicators.
* The AI should clearly distinguish between direct pest detection and symptom-based inference.

---

### 12. Support for Additional Crops
* Expand the system beyond a single crop.
* Add additional crops and corresponding:
  * Pest datasets
  * Disease datasets
  * Plant health indicators
  * Pest identification models
  * Pesticide/insecticide recommendation records
* The system architecture should be designed so that new crops can be added without requiring major changes to the entire system.

---

### 13. AI-Based Plant Health Assessment
* Enhance the AI system so it can assess the overall health condition of the plant in addition to detecting pests.
* The system should investigate the detection of:
  * Mold/fungal growth
  * Visible diseases
  * Discoloration
  * Leaf damage
  * Wilting
  * Abnormal plant appearance
  * Other visible indicators of poor plant health
* The AI should provide a plant-health assessment together with the pest detection result.

---

### 14. Integrated AI Detection Workflow

The enhanced system should generally follow this workflow:

$$\text{Crop} \longrightarrow \text{Camera / Image Capture} \longrightarrow \text{AI Image Processing} \longrightarrow \text{Pest \& Plant Health Detection} \longrightarrow \text{Pest Counting} \longrightarrow \text{Confidence Assessment} \longrightarrow \text{Pesticide / Insecticide Recommendation} \longrightarrow \text{Database Storage} \longrightarrow \text{Web / Mobile Display} \longrightarrow \text{Notification / Monitoring}$$

**Conditional Target Detection Trigger:**
If a target pest is detected, the robot executes:
$$\text{Detect Pest} \longrightarrow \text{Stop / Pause} \longrightarrow \text{Capture Additional Image} \longrightarrow \text{Confirm Detection} \longrightarrow \text{Generate Recommendation} \longrightarrow \text{Store Results} \longrightarrow \text{Notify User}$$