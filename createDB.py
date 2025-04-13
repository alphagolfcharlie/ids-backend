import sqlite3 
DB_name = 'routes.db'
def init_db():
    conn = sqlite3.connect(DB_name)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS routes (
            origin TEXT,
            destination TEXT,
            route TEXT,
            altitude TEXT,
            notes TEXT
        )
    ''')
    routes = [("CLE", "ORD", "GTLKE4 DAIFE WATSN WATSN4", "", ""),
    ("CLE", "MDW", "GTLKE4 BAGEL PANGG5", "", ""),
    ("CLE", "MKE", "GTLKE4 ALPHE PEGEE GETCH LYSTR SUDDS", "", ""),
    ("CLE", "BOS", "PFLYD1 JASEE JHW Q82 PONCT JFUND2", "", ""),
    ("CLE", "BDL", "PFLYD1 JASEE JHW Q82 MEMMS WILET STELA1", "", ""),
    ("CLE", "BWI", "KKIDS1 NUSMM ANTHM5", "", ""),
    ("CLE", "DCA", "KKIDS1 NUSMM BUCKO FRDMM6", "", ""),
    ("CLE", "IAD", "KKIDS1 NUSMM MGW GIBBZ5", "", ""),
    ("CLE", "ORF", "KKIDS1 NUSMM MGW MOL TERKS2", "", ""),
    ("CLE", "CMH", "WWSHR CBUSS2", "", ""),
    ("CLE", "CVG", "CAVVS4 CAVVS UKATS TIGGR4", "FL220B", ""),
    ("CLE", "IND", "ZAAPA5 SINKR SNKPT2", "FL220B", ""),
    ("CLE", "SDF", "CAVVS4 CAVVS UKATS DLAMP8", "FL280B", ""),
    ("CLE", "MSP", "GTLKE4 ALPHE VIO KAMMA KKILR3", "", "Through ZAU"),
    ("CLE", "EWR", "PFLYD1 DORET J584 SLT FQM3", "", ""),
    ("CLE", "JFK", "PFLYD1 JASEE JHW J70 LVZ LENDY8", "", ""),
    ("CLE", "LGA", "PFLYD1 MAAJR ETG MIP4", "", ""),
    ("CLE", "PHL", "KKIDS1 EWC JST BOJID4", "", ""),
    ("CLE", "YYZ", "PFLYD1 PATRC FINGL NUBER6", "FL190B", ""),
    ("CLE", "DTW", "BONZZ BONZZ2", "", "DTW south"),
    ("CLE", "DTW", "BONZZ KLYNK3", "", "DTW north"),
    ("BUF", "ORD", "DAVVK FARGN CHAAP Q436 EMMMA WYNDE2", "", ""),
    ("BUF", "MDW", "JHW DJB J60 ASHEN BAGEL PANGG5", "", ""),
    ("BUF", "BOS", "GEE PONCT JFUND2", "", ""),
    ("BUF", "MKE", "DERLO Q935 HOCKE GETCH LYSTR SUDDS", "", ""),
    ("BUF", "BDL", "GEE BEEPS WILET STELA1", "", ""),
    ("BUF", "BWI", "VAIRS DDUBS IZZEE TRISH4", "", "Through ZNY"),
    ("BUF", "DCA", "VAIRS PSB SKILS5", "", "Through ZNY"),
    ("BUF", "IAD", "VAIRS PSB WAYNZ1", "", "Through ZNY"),
    ("BUF", "CMH", "JHW WWSHR CBUSS2", "", ""),
    ("BUF", "CVG", "DKK ACO UKATS TIGRR4", "", ""),
    ("BUF", "IND", "JHW DJB RINTE SNKPT2", "", ""),
    ("BUF", "SDF", "JHW UKATS DLAMP8", "", ""),
    ("BUF", "MSP", "DERLO HOCKE IDIOM MUSCL3", "", ""),
    ("BUF", "EWR", "GEE BEEPS Q140 KODEY HNK FLOSI4", "", ""),
    ("BUF", "JFK", "GEE BEEPS IGN IGN1", "", ""),
    ("BUF", "LGA", "GEE RKA HAARP4", "", ""),
    ("BUF", "PHL", "BFD PSB BOJID4", "", ""),
    ("BUF", "YYZ", "ISTON LINNG3", "16000B", ""),
    ("BUF", "DTW", "DONEO TPGUN2", "", "DTW south"),
    ("BUF", "DTW", "DONEO CUUGR", "", "DTW north"),
    ("DTW", "ORD", "KAYLN3 SMUUV WYNDE2", "FL280B", ""),
    ("DTW", "MDW", "CCOBB3 ZEGBI LEROY BAGEL PANGG5", "FL220B", ""),
    ("DTW", "BOS", "HHOWE4 LNCON JHW Q82 PONCT JFUND2", "", ""),
    ("DTW", "MKE", "MIGGY3 GETCH LYSTR SUDDS", "", ""),
    ("DTW", "BDL", "HHOWE4 LNCON JHW Q82 MEMMS WILET STELA1", "", ""),
    ("DTW", "BWI", "LIDDS3 GRIVY NUSMM ANTHM5", "", ""),
    ("DTW", "DCA", "LIDDS3 GRIVY BUCKO FRDMM6", "", ""),
    ("DTW", "IAD", "LIDDS3 GRIVY AIR MGW GIBBZ5", "", ""),
    ("DTW", "CMH", "CLVIN3 CLVIN ESSIE DUBLN1", "", ""),
    ("DTW", "CVG", "SNDRS3 TORRR DEBAR ARBAS RID MEEKR", "FL200B", ""),
    ("DTW", "IND", "SNDRS3 TORRR SNKPT CLANG7", "FL220B", ""),
    ("DTW", "SDF", "CLVIN3 CLVIN RINTE DLAMP8", "FL280B", ""),
    ("DTW", "MSP", "MIGGY3 SLLAP Q440 IDIOM MUSCL3", "", "Preferred"),
    ("DTW", "EWR", "KAYLN3 SMUUV KAMMA KKILR3", "", "Through ZAU"),
    ("DTW", "JFK", "PAVYL3 MRDOC HOXIE J70 LVZ LENDY8", "", ""),
    ("DTW", "LGA", "PAVYL3 ESSBE CXR ETG MIP4", "", ""),
    ("DTW", "PHL", "PAVYL3 ESSBE CXR EWC JST BOJID4", "", ""),
    ("DTW", "YYZ", "ZETTR4 TANKO APDAX NUBER6", "FL210B", ""),
    ("DTW", "CLE", "KZLOV2 WINNZ BRWNZ4", "", ""),
    ("DTW", "BUF", "HHOWE4 BROKK DKK", "FL270B", "")]

    cursor.executemany('INSERT INTO routes VALUES (?, ?, ?, ?, ?)',routes)
    conn.commit()
    conn.close()
init_db()