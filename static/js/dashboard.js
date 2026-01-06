document.addEventListener('DOMContentLoaded', function() {
  (function() {
    console.log("DOM fully loaded and script executing.");

    const dataElement = document.getElementById('conquered-data');
    let conquered_quest_data = []; // Default to an empty array
    if (dataElement) {
      const conqueredJSON = dataElement.getAttribute('data-conquered');
      try {
        if (conqueredJSON) {
          conquered_quest_data = JSON.parse(conqueredJSON);
        }
      } catch (e) {
        console.error("Error parsing conquered list JSON:", e, conqueredJSON);
      }
    } else {
      console.error('Error: Data element #conquered-data not found.');
    }
    
    let currentMapType = 'europe';

    // 挑戦回数に応じた「色コード」を返す関数
    function getAttemptTierColor(attempts) {
      if (attempts >= 7) return '#ff6f00'; // tier-4
      if (attempts >= 5) return '#ff8f00'; // tier-3
      if (attempts >= 3) return '#ffa000'; // tier-2
      if (attempts >= 1) return '#ffc107'; // tier-1
      return '#e0e0e0'; // デフォルトの色（未制覇）
    }

    function highlightMap(mapType) {
        const svgObject = document.querySelector(`#map-${mapType} object`);
        if (!svgObject) return;

        const onSvgLoad = () => {
            const svgDoc = svgObject.contentDocument;
            if (!svgDoc) return;

            // いったんすべての色とクラスをリセット
            svgDoc.querySelectorAll('path, rect').forEach(p => {
              p.classList.remove('conquered', 'attempt-tier-1', 'attempt-tier-2', 'attempt-tier-3', 'attempt-tier-4');
              p.style.fill = ''; // 直接指定したfillをリセット
            });

            if (Array.isArray(conquered_quest_data)) {
              const questsForThisMap = conquered_quest_data.filter(item => item.map_type === mapType);

              questsForThisMap.forEach(item => {
                  const element = svgDoc.getElementById(String(item.quest_id));
                  if (element) {
                      const fillColor = getAttemptTierColor(item.attempts);
                      element.style.fill = fillColor; // 色を直接設定
                      element.classList.add('conquered'); // 枠線用のクラスは引き続き使用
                  }
              });
            }
        };

        if (svgObject.contentDocument && svgObject.contentDocument.readyState === 'complete') {
            onSvgLoad();
        } else {
            svgObject.addEventListener('load', onSvgLoad);
        }
    }

    const mapContainer = document.querySelector('.map-container');

    // 背景画像を更新する関数
    function updateBackground(mapType) {
        let imageUrl = '';
        switch (mapType) {
            case 'europe':
                imageUrl = "url('/static/maps/Europe.png')";
                break;
            case 'americus':
                imageUrl = "url('/static/maps/Americus.png')";
                break;
            case 'zipangu':
                imageUrl = "url('/static/maps/Zipangu.png')";
                break;
            default:
                imageUrl = "url('/static/maps/world.svg')"; // デフォルト
        }
        if (mapContainer) {
            mapContainer.style.backgroundImage = imageUrl;
        }
    }

    function switchMap(type) {
        currentMapType = type;
        document.querySelectorAll('.map').forEach(m => m.classList.remove('active'));
        const newMap = document.getElementById(`map-${type}`);
        if (newMap) {
            newMap.classList.add('active');
        }
        highlightMap(type);
        updateBackground(type); // 背景画像を更新
    }

    // Add click listeners to buttons
    const buttons = document.querySelectorAll('.map-selector button');
    buttons.forEach(button => {
        button.addEventListener('click', (event) => {
            const type = event.currentTarget.dataset.mapType;
            if (!type) return;

            document.querySelectorAll('.map-selector button').forEach(btn => {
                btn.classList.remove('active', 'btn-primary');
                btn.classList.add('btn-secondary');
            });
            event.currentTarget.classList.add('active', 'btn-primary');
            event.currentTarget.classList.remove('btn-secondary');
            
            switchMap(type);
        });
    });

    // Initial Load
    document.querySelectorAll('.map').forEach(m => m.classList.remove('active'));
    const initialMap = document.getElementById(`map-${currentMapType}`);
    if (initialMap) {
        initialMap.classList.add('active');
    }
    highlightMap(currentMapType);
    updateBackground(currentMapType); // 初期背景を設定

    // Add listeners for subsequent loads to handle caching
    document.querySelectorAll('.map object').forEach(obj => {
        obj.addEventListener('load', () => {
            const mapId = obj.parentElement.id.split('-')[1];
            highlightMap(mapId);
        });
    });
  })();
});